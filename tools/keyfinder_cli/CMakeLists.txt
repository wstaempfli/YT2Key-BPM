cmake_minimum_required(VERSION 3.16)
project(keyfinder_cli LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(LIBKEYFINDER_DIR "${CMAKE_CURRENT_LIST_DIR}/../../libKeyFinder")
list(APPEND CMAKE_MODULE_PATH "${LIBKEYFINDER_DIR}/cmake")
find_package(FFTW REQUIRED)

add_library(keyfinder_local STATIC
  "${LIBKEYFINDER_DIR}/audiodata.cpp"
  "${LIBKEYFINDER_DIR}/chromagram.cpp"
  "${LIBKEYFINDER_DIR}/chromatransform.cpp"
  "${LIBKEYFINDER_DIR}/chromatransformfactory.cpp"
  "${LIBKEYFINDER_DIR}/fftadapter.cpp"
  "${LIBKEYFINDER_DIR}/keyclassifier.cpp"
  "${LIBKEYFINDER_DIR}/keyfinder.cpp"
  "${LIBKEYFINDER_DIR}/lowpassfilter.cpp"
  "${LIBKEYFINDER_DIR}/lowpassfilterfactory.cpp"
  "${LIBKEYFINDER_DIR}/spectrumanalyser.cpp"
  "${LIBKEYFINDER_DIR}/temporalwindowfactory.cpp"
  "${LIBKEYFINDER_DIR}/toneprofiles.cpp"
  "${LIBKEYFINDER_DIR}/windowfunctions.cpp"
  "${LIBKEYFINDER_DIR}/workspace.cpp"
  "${LIBKEYFINDER_DIR}/constants.cpp"
)
target_include_directories(keyfinder_local PUBLIC "${LIBKEYFINDER_DIR}")
target_link_libraries(keyfinder_local PUBLIC FFTW::FFTW)

add_executable(keyfinder_cli main.cpp)
target_link_libraries(keyfinder_cli PRIVATE keyfinder_local)
