import os
import re
import sys
import platform
import subprocess
import shutil
import warnings

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext


def parse_cmake_version(output):
    match = re.search(r'version\s*([\d.]+)', output)
    if not match:
        return 0, 0, 0
    parts = [int(part) for part in match.group(1).split('.')]
    return tuple((parts + [0, 0, 0])[:3])


def get_cmake_arg_value(args, option):
    for index, arg in enumerate(args):
        if arg == option and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith(option + '='):
            return arg.split('=', 1)[1]
    return ''


def read_cmake_cache_value(build_dir, key):
    cache_path = os.path.join(build_dir, 'CMakeCache.txt')
    if not os.path.exists(cache_path):
        return ''
    pattern = re.compile(r'^{}(?::[^=]*)?=(.*)$'.format(re.escape(key)))
    with open(cache_path, 'r', encoding='utf-8', errors='ignore') as cache_file:
        for line in cache_file:
            match = pattern.match(line.strip())
            if match:
                return match.group(1)
    return ''


def clear_cmake_cache(build_dir):
    cache_path = os.path.join(build_dir, 'CMakeCache.txt')
    files_path = os.path.join(build_dir, 'CMakeFiles')
    if os.path.isfile(cache_path):
        os.remove(cache_path)
    if os.path.isdir(files_path):
        shutil.rmtree(files_path)


def safe_build_dir_name(*parts):
    name = '-'.join(part for part in parts if part)
    name = re.sub(r'[^A-Za-z0-9_.-]+', '-', name).strip('-')
    return name.lower() or 'default'


def merge_path(preferred, existing):
    if not preferred:
        return existing
    if not existing:
        return preferred
    return preferred + os.pathsep + existing


def path_candidates(*parts):
    path = os.path.join(*parts)
    return path if os.path.isdir(path) else None


def normalized_env(source):
    if platform.system() != "Windows":
        return source.copy()
    return {key.upper(): value for key, value in source.items()}


def find_pybind11_cmake_dir():
    try:
        import pybind11
    except ImportError:
        return ''

    get_cmake_dir = getattr(pybind11, 'get_cmake_dir', None)
    if not get_cmake_dir:
        return ''

    cmake_dir = get_cmake_dir()
    return cmake_dir if cmake_dir and os.path.isdir(cmake_dir) else ''


class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)


class CMakeBuild(build_ext):
    required_cmake_version = (3, 14, 0)

    def run(self):
        try:
            out = subprocess.check_output(['cmake', '--version']).decode()
        except OSError:
            raise RuntimeError("CMake must be installed to build the following extensions: " +
                               ", ".join(e.name for e in self.extensions))

        cmake_version = parse_cmake_version(out)
        if cmake_version < self.required_cmake_version:
            raise RuntimeError("CMake >= {}.{}.{} is required".format(*self.required_cmake_version))

        for ext in self.extensions:
            self.build_extension(ext)

    @staticmethod
    def which_in_env(command, env):
        return shutil.which(command, path=env.get('PATH', os.environ.get('PATH', '')))

    def find_msvc_env(self):
        try:
            from setuptools._distutils import _msvccompiler
            from setuptools._distutils.util import get_platform
        except ImportError:
            return None

        platform_name = get_platform()
        plat_to_vcvars = getattr(_msvccompiler, 'PLAT_TO_VCVARS', {
            'win32': 'x86',
            'win-amd64': 'x86_amd64',
            'win-arm32': 'x86_arm',
            'win-arm64': 'x86_arm64',
        })
        vcvars_platform = plat_to_vcvars.get(platform_name)
        if not vcvars_platform:
            return None

        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                get_vc_env = getattr(_msvccompiler, '_get_vc_env', None)
                if not get_vc_env:
                    raise RuntimeError("setuptools._distutils._msvccompiler._get_vc_env is unavailable")
                vc_env = get_vc_env(vcvars_platform)
                if vc_env:
                    return vc_env
        except Exception:
            pass

        try:
            from setuptools import msvc
            return msvc.EnvironmentInfo(vcvars_platform).return_env()
        except Exception:
            return None

    def apply_msvc_env(self, env):
        if self.which_in_env('cl', env) and env.get('INCLUDE') and env.get('LIB'):
            return True

        vc_env = self.find_msvc_env()
        if not vc_env:
            return False

        for key, value in vc_env.items():
            upper_key = key.upper()
            if upper_key == 'PATH':
                env['PATH'] = merge_path(value, env.get('PATH', ''))
            else:
                env[upper_key] = value
        if 'path' in vc_env:
            env['PATH'] = merge_path(vc_env['path'], env.get('PATH', ''))

        vc_tools_install_dir = vc_env.get('vctoolsinstalldir') or vc_env.get('VCToolsInstallDir')
        if vc_tools_install_dir:
            target_arch = 'x64' if sys.maxsize > 2**32 else 'x86'
            host_arch = 'x64' if platform.machine().lower() in ('amd64', 'x86_64') else 'x86'
            bin_dirs = [
                path_candidates(vc_tools_install_dir, 'bin', 'Host' + host_arch, target_arch),
                path_candidates(vc_tools_install_dir, 'bin', 'Hostx64', target_arch),
                path_candidates(vc_tools_install_dir, 'bin', 'Hostx86', target_arch),
            ]
            for bin_dir in reversed([entry for entry in bin_dirs if entry]):
                env['PATH'] = merge_path(bin_dir, env.get('PATH', ''))

        return bool(self.which_in_env('cl', env))

    def find_visual_studio_generator(self):
        program_files_x86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
        vswhere = os.path.join(
            program_files_x86,
            'Microsoft Visual Studio',
            'Installer',
            'vswhere.exe',
        )
        if not os.path.exists(vswhere):
            return None

        try:
            version = subprocess.check_output([
                vswhere,
                '-latest',
                '-products', '*',
                '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                '-property', 'installationVersion',
            ]).decode(errors='ignore').strip()
        except (OSError, subprocess.CalledProcessError):
            return None

        if version.startswith('17.'):
            return 'Visual Studio 17 2022'
        if version.startswith('16.'):
            return 'Visual Studio 16 2019'
        if version.startswith('15.'):
            return 'Visual Studio 15 2017'
        return None

    def configure_windows_generator(self, cmake_args, cfg, env):
        self.apply_msvc_env(env)

        generator = os.environ.get('CMAKE_GENERATOR', '')
        generator_platform = os.environ.get('CMAKE_GENERATOR_PLATFORM', '')
        generator_lower = generator.lower()

        single_config_generators = ('ninja', 'nmake makefiles', 'mingw makefiles')
        is_single_config = any(name in generator_lower for name in single_config_generators)

        if is_single_config:
            cmake_args += ['-DCMAKE_BUILD_TYPE=' + cfg]
            if 'ninja' in generator_lower and not os.environ.get('CMAKE_MAKE_PROGRAM'):
                ninja = self.which_in_env('ninja', env)
                if ninja:
                    cmake_args += ['-DCMAKE_MAKE_PROGRAM=' + ninja]
            elif 'nmake' in generator_lower and not os.environ.get('CMAKE_MAKE_PROGRAM'):
                nmake = self.which_in_env('nmake', env)
                if nmake:
                    cmake_args += ['-DCMAKE_MAKE_PROGRAM=' + nmake]
            return

        if 'visual studio' in generator_lower:
            if not generator_platform:
                cmake_args += ['-A', 'x64' if sys.maxsize > 2**32 else 'Win32']
            return

        if generator:
            return

        ninja = self.which_in_env('ninja', env)
        if ninja:
            cmake_args += ['-G', 'Ninja', '-DCMAKE_BUILD_TYPE=' + cfg]
            cmake_args += ['-DCMAKE_MAKE_PROGRAM=' + ninja]
            return

        nmake = self.which_in_env('nmake', env)
        if self.which_in_env('cl', env) and nmake:
            cmake_args += ['-G', 'NMake Makefiles', '-DCMAKE_BUILD_TYPE=' + cfg]
            cmake_args += ['-DCMAKE_MAKE_PROGRAM=' + nmake]
            return

        visual_studio_generator = self.find_visual_studio_generator()
        if visual_studio_generator:
            cmake_args += ['-G', visual_studio_generator]
            cmake_args += ['-A', 'x64' if sys.maxsize > 2**32 else 'Win32']
            return

        if not self.which_in_env('cl', env):
            raise RuntimeError(
                "A Windows C++ compiler was not found. Install Visual Studio Build Tools 2022 "
                "with 'Desktop development with C++', including MSVC v143 and a Windows SDK; "
                "then rerun 'python -m pip install .'. If the tools are already installed, "
                "run the command from 'x64 Native Tools Command Prompt for VS 2022' or set "
                "CMAKE_GENERATOR to a configured compiler toolchain."
            )

        if sys.maxsize > 2**32:
            cmake_args += ['-A', 'x64']
        else:
            cmake_args += ['-A', 'Win32']

    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        cmake_args = ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY=' + extdir,
                      '-DPYTHON_EXECUTABLE=' + sys.executable,
                      '-DVERSION="' + self.distribution.get_version() + '"']
        pybind11_cmake_dir = find_pybind11_cmake_dir()
        if pybind11_cmake_dir:
            cmake_args += ['-Dpybind11_DIR=' + pybind11_cmake_dir]

        cfg = 'Debug' if self.debug else 'Release'
        build_args = ['--config', cfg]
        if 'CMAKE_BUILD_PARALLEL_LEVEL' not in os.environ:
            build_args += ['--parallel', str(os.cpu_count() or 2)]

        env = normalized_env(os.environ)

        if platform.system() == "Windows":
            cmake_args += ['-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}'.format(cfg.upper(), extdir)]
            self.configure_windows_generator(cmake_args, cfg, env)
        else:
            cmake_args += ['-DCMAKE_BUILD_TYPE=' + cfg]

        generator = get_cmake_arg_value(cmake_args, '-G') or os.environ.get('CMAKE_GENERATOR', 'default')
        generator_platform = get_cmake_arg_value(cmake_args, '-A') or os.environ.get('CMAKE_GENERATOR_PLATFORM', '')
        generator_toolset = get_cmake_arg_value(cmake_args, '-T') or os.environ.get('CMAKE_GENERATOR_TOOLSET', '')
        make_program = get_cmake_arg_value(cmake_args, '-DCMAKE_MAKE_PROGRAM') or os.environ.get('CMAKE_MAKE_PROGRAM', '')
        build_temp = os.path.join(self.build_temp, safe_build_dir_name(generator, generator_platform, generator_toolset))

        if not os.path.exists(build_temp):
            os.makedirs(build_temp)
        cached_generator = read_cmake_cache_value(build_temp, 'CMAKE_GENERATOR')
        cached_make_program = read_cmake_cache_value(build_temp, 'CMAKE_MAKE_PROGRAM')
        stale_make_program = cached_make_program and os.path.isabs(cached_make_program) and not os.path.exists(cached_make_program)
        changed_make_program = (
            make_program and cached_make_program and
            os.path.abspath(cached_make_program).lower() != os.path.abspath(make_program).lower()
        )
        if (cached_generator and cached_generator != generator) or stale_make_program or changed_make_program:
            clear_cmake_cache(build_temp)
        try:
            subprocess.check_call(['cmake', ext.sourcedir] + cmake_args, cwd=build_temp, env=env)
            subprocess.check_call(['cmake', '--build', '.', '--target', 'cityflow'] + build_args, cwd=build_temp, env=env)
        except subprocess.CalledProcessError as exc:
            if platform.system() == "Windows":
                raise RuntimeError(
                    "CMake build failed. On Windows, install Visual Studio Build Tools "
                    "with the C++ workload, or set CMAKE_GENERATOR to a configured "
                    "MSVC generator such as 'NMake Makefiles' from a Developer Command Prompt."
                ) from exc
            raise


setup(
    name='CityFlow',
    version='0.1',
    author='Huichu Zhang',
    author_email='zhc@apex.sjtu.edu.cn',
    description='CityFlow: A Multi-Agent Reinforcement Learning Environment for Large Scale City Traffic Scenario',
    long_description='',
    ext_modules=[CMakeExtension('cityflow')],
    cmdclass=dict(build_ext=CMakeBuild),
    zip_safe=False
)
