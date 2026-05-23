# CityFlow

CityFlow is a multi-agent reinforcement learning environment for large-scale city traffic scenario.

## Source and Windows Build Changes

This source tree is based on the upstream CityFlow source repository:

- [cityflow-project/CityFlow.git](https://github.com/cityflow-project/CityFlow.git)

This version keeps the CityFlow simulator/source implementation unchanged and only adjusts
the build and dependency configuration so the package can be built and installed from
source on Windows.

The Windows build changes include:

- modern Python build metadata through `pyproject.toml`;
- CMake configuration updates for MSVC-compatible compiler options;
- automatic MSVC environment discovery during `pip install .`;
- stable CMake build directories for different Windows generators;
- explicit Ninja/NMake build tool configuration to avoid stale CMake cache paths;
- dependency fallback support for `pybind11` and RapidJSON when vendored submodules
  are unavailable.

## Build Requirements

Windows source builds require the following tools:

- 64-bit Python and `pip`. The Windows build has been verified with Python 3.13
  on `win_amd64`.
- Visual Studio Build Tools with the **Desktop development with C++** workload.
- MSVC x64/x86 build tools, for example MSVC v143 or newer.
- A Windows SDK, for example Windows 10 SDK or Windows 11 SDK.
- CMake 3.14 or newer.
- Ninja or NMake. Ninja is preferred; it is installed as a Python build dependency
  by `pyproject.toml` and may also be provided by Visual Studio.
- Internet access for the first build when third-party dependencies need to be
  downloaded.

The Python build isolation environment installs these build dependencies automatically:

- `setuptools`
- `wheel`
- `cmake`
- `ninja`
- `pybind11`

## Install from Source Code

This modified source tree can be installed directly. The upstream repository is
listed for provenance; cloning the upstream repository alone does not include
these Windows build-configuration changes.

If you need to recreate this tree from upstream, start from:

```powershell
git clone https://github.com/cityflow-project/CityFlow.git
cd CityFlow
```

Then apply the Windows build and dependency configuration changes from this
modified source tree before installing.

If submodules are used, initialize them before building:

```powershell
git submodule update --init --recursive
```

Install the package from source:

```powershell
python -m pip install .
```

Verify the installation:

```powershell
python -c "import cityflow; print(cityflow.__file__); print(cityflow.__version__)"
```

On Windows, this should build and install a `cityflow` extension module similar to:

```text
cityflow.cp313-win_amd64.pyd
```

If CMake reports a generator mismatch or a stale Ninja/NMake path, remove the local
`build` directory and run the install command again:

```powershell
Remove-Item -Recurse -Force build
python -m pip install .
```
