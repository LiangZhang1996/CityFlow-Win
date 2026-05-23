cmake_minimum_required(VERSION 3.14)
project(cityflow LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(POLICY CMP0063)
  cmake_policy(SET CMP0063 NEW)
endif()

if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

function(cityflow_apply_compile_options target_name)
    if(MSVC)
        target_compile_options(${target_name} PRIVATE /W3 /EHsc /bigobj /MP)
    else()
        target_compile_options(${target_name} PRIVATE
            -Wall
            $<$<CONFIG:Release>:-O2>
            $<$<CONFIG:Debug>:-g>
        )
    endif()
endfunction()

option(CITYFLOW_FETCH_DEPS "Fetch third-party dependencies when submodules are unavailable" ON)
set(CITYFLOW_PYBIND11_GIT_TAG "v2.13.6" CACHE STRING "pybind11 tag used when fetching dependencies")
set(CITYFLOW_RAPIDJSON_GIT_TAG "7b3d971b261ab624f745e9450b1620157e39cce5" CACHE STRING "RapidJSON commit used when fetching dependencies")

include(FetchContent)

set(CITYFLOW_MILO_INCLUDE_DIR "${PROJECT_SOURCE_DIR}/extern/milo")

if(EXISTS "${PROJECT_SOURCE_DIR}/extern/pybind11/CMakeLists.txt")
    message(STATUS "Using vendored pybind11")
    add_subdirectory(extern/pybind11)
else()
    find_package(pybind11 CONFIG QUIET)
    if(pybind11_FOUND)
        message(STATUS "Using installed pybind11")
    else()
        if(NOT CITYFLOW_FETCH_DEPS)
            message(FATAL_ERROR "pybind11 was not found. Update submodules, install pybind11, or configure with CITYFLOW_FETCH_DEPS=ON.")
        endif()
        message(STATUS "Fetching pybind11 ${CITYFLOW_PYBIND11_GIT_TAG}")
        FetchContent_Declare(
            pybind11
            GIT_REPOSITORY https://github.com/pybind/pybind11.git
            GIT_TAG ${CITYFLOW_PYBIND11_GIT_TAG}
        )
        FetchContent_MakeAvailable(pybind11)
    endif()
endif()

if(EXISTS "${PROJECT_SOURCE_DIR}/extern/rapidjson/include/rapidjson/document.h")
    message(STATUS "Using vendored RapidJSON")
    set(CITYFLOW_RAPIDJSON_INCLUDE_DIR "${PROJECT_SOURCE_DIR}/extern/rapidjson/include")
else()
    find_path(CITYFLOW_RAPIDJSON_SYSTEM_INCLUDE_DIR NAMES rapidjson/document.h)
    if(CITYFLOW_RAPIDJSON_SYSTEM_INCLUDE_DIR)
        message(STATUS "Using installed RapidJSON")
        set(CITYFLOW_RAPIDJSON_INCLUDE_DIR "${CITYFLOW_RAPIDJSON_SYSTEM_INCLUDE_DIR}")
    else()
        if(NOT CITYFLOW_FETCH_DEPS)
            message(FATAL_ERROR "RapidJSON was not found. Update submodules, install RapidJSON, or configure with CITYFLOW_FETCH_DEPS=ON.")
        endif()
        message(STATUS "Fetching RapidJSON ${CITYFLOW_RAPIDJSON_GIT_TAG}")
        FetchContent_Declare(
            rapidjson
            GIT_REPOSITORY https://github.com/cityflow-project/rapidjson.git
            GIT_TAG ${CITYFLOW_RAPIDJSON_GIT_TAG}
        )
        FetchContent_GetProperties(rapidjson)
        if(NOT rapidjson_POPULATED)
            FetchContent_Populate(rapidjson)
        endif()
        set(CITYFLOW_RAPIDJSON_INCLUDE_DIR "${rapidjson_SOURCE_DIR}/include")
    endif()
endif()

add_subdirectory(src)

# Tests
find_package(GTest)
if(GTEST_FOUND)
    enable_testing()
    add_subdirectory(tests)
endif()

if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_subdirectory(tools/debug)
endif()

pybind11_add_module(${PROJECT_NAME} MODULE src/cityflow.cpp)
cityflow_apply_compile_options(${PROJECT_NAME})
target_link_libraries(${PROJECT_NAME} PRIVATE ${PROJECT_LIB_NAME})
if(VERSION)
    target_compile_definitions(${PROJECT_NAME} PRIVATE VERSION=${VERSION})
endif()

