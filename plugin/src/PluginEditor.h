#pragma once

#include <atomic>
#include <functional>
#include <memory>

#include <JuceHeader.h>

#include "PluginProcessor.h"

class FlBeatDownloaderEditor : public juce::AudioProcessorEditor, private juce::Timer {
public:
  explicit FlBeatDownloaderEditor(FlBeatDownloaderProcessor&);
  ~FlBeatDownloaderEditor() override;

  void paint(juce::Graphics&) override;
  void resized() override;

private:
  struct ApiResponse {
    int statusCode = 0;
    juce::String body;
  };

  void timerCallback() override;
  void refreshUiFromState();
  void submitJob();
  void cancelJob();
  void fetchStatus();
  void fetchRecentJobs();
  void pingService();
  void startService();
  void stopService();
  void ensureServiceRunning();
  juce::File resolveCompanionRoot() const;
  bool isValidCompanionRoot(const juce::File& root) const;
  void runRequestAsync(const juce::String& path, const juce::String& method, const juce::String& body);
  void runGetAsync(const juce::String& path, std::function<void(ApiResponse)> callback);
  void runGetJobsAsync(const juce::String& path, std::function<void(ApiResponse)> callback);
  void appendLog(const juce::String& line);

  FlBeatDownloaderProcessor& processorRef;

  juce::Label titleLabel;
  juce::Label urlLabel;
  juce::TextEditor urlEditor;
  juce::ToggleButton singleModeToggle;
  juce::Label limitLabel;
  juce::TextEditor limitEditor;
  juce::Label targetDirLabel;
  juce::TextEditor targetDirEditor;
  juce::TextButton chooseDirButton;
  juce::TextButton startButton;
  juce::TextButton cancelButton;
  juce::TextButton serviceStartButton;
  juce::TextButton serviceStopButton;
  juce::Label statusLabel;
  juce::ProgressBar progressBar;
  juce::TextEditor logBox;
  juce::Label recentJobsLabel;
  juce::TextEditor recentJobsBox;
  double progressValue = 0.0;

  juce::String activeJobId;
  juce::String serviceBaseUrl {"http://127.0.0.1:8765"};
  std::atomic<bool> postInFlight {false};
  std::atomic<bool> statusInFlight {false};
  std::atomic<bool> healthInFlight {false};
  std::atomic<bool> jobsInFlight {false};
  juce::String latestStatusText {"Idle"};
  juce::String lastLoggedStatus;
  bool serviceHealthy = false;
  bool lastServiceHealthy = false;
  int timerTicks = 0;
  std::unique_ptr<juce::FileChooser> directoryChooser;

  JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(FlBeatDownloaderEditor)
};
