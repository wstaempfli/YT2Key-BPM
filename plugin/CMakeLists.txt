cmake_minimum_required(VERSION 3.22)
project(FlBeatDownloaderPlugin VERSION 0.1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Set JUCE_DIR to your local JUCE checkout before configuring.
# Example: cmake -S plugin -B plugin/build -DJUCE_DIR=/path/to/JUCE
if(NOT DEFINED JUCE_DIR)
  message(FATAL_ERROR "Please set JUCE_DIR to your JUCE path")
endif()

add_subdirectory("${JUCE_DIR}" JUCE)

juce_add_plugin(FlBeatDownloaderPlugin
  COMPANY_NAME "Local"
  BUNDLE_ID "local.flbeatdownloader"
  PLUGIN_MANUFACTURER_CODE FLBD
  PLUGIN_CODE FbDl
  FORMATS VST3
  IS_SYNTH FALSE
  NEEDS_MIDI_INPUT FALSE
  NEEDS_MIDI_OUTPUT FALSE
  IS_MIDI_EFFECT FALSE
  EDITOR_WANTS_KEYBOARD_FOCUS TRUE
  COPY_PLUGIN_AFTER_BUILD FALSE
  PRODUCT_NAME "FL Beat Downloader"
)

juce_generate_juce_header(FlBeatDownloaderPlugin)

target_sources(FlBeatDownloaderPlugin PRIVATE
  src/PluginProcessor.cpp
  src/PluginProcessor.h
  src/PluginEditor.cpp
  src/PluginEditor.h
)

target_compile_definitions(FlBeatDownloaderPlugin PRIVATE
  JUCE_WEB_BROWSER=0
  JUCE_USE_CURL=1
  JUCE_VST3_CAN_REPLACE_VST2=0
)

target_link_libraries(FlBeatDownloaderPlugin PRIVATE
  juce::juce_audio_utils
  juce::juce_gui_extra
)
