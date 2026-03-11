#include "PluginProcessor.h"
#include "PluginEditor.h"

FlBeatDownloaderProcessor::FlBeatDownloaderProcessor()
    : juce::AudioProcessor(BusesProperties().withOutput("Output", juce::AudioChannelSet::stereo(), true)) {}

void FlBeatDownloaderProcessor::prepareToPlay(double, int) {}

void FlBeatDownloaderProcessor::releaseResources() {}

bool FlBeatDownloaderProcessor::isBusesLayoutSupported(const BusesLayout& layouts) const {
  return layouts.getMainOutputChannelSet() == juce::AudioChannelSet::stereo() ||
         layouts.getMainOutputChannelSet() == juce::AudioChannelSet::mono();
}

void FlBeatDownloaderProcessor::processBlock(juce::AudioBuffer<float>& buffer, juce::MidiBuffer&) {
  juce::ScopedNoDenormals noDenormals;
  for (int channel = getTotalNumInputChannels(); channel < getTotalNumOutputChannels(); ++channel) {
    buffer.clear(channel, 0, buffer.getNumSamples());
  }
}

juce::AudioProcessorEditor* FlBeatDownloaderProcessor::createEditor() {
  return new FlBeatDownloaderEditor(*this);
}

const juce::String FlBeatDownloaderProcessor::getName() const {
  return "FL Beat Downloader";
}

void FlBeatDownloaderProcessor::getStateInformation(juce::MemoryBlock& destData) {
  juce::MemoryOutputStream stream(destData, true);
  stream.writeInt(1);
}

void FlBeatDownloaderProcessor::setStateInformation(const void*, int) {}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() {
  return new FlBeatDownloaderProcessor();
}
