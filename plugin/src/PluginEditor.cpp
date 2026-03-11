#include "PluginEditor.h"

#include <cstdlib>
#include <thread>
#include <vector>

namespace {
constexpr int kPadding = 10;
}

FlBeatDownloaderEditor::FlBeatDownloaderEditor(FlBeatDownloaderProcessor& p)
    : AudioProcessorEditor(&p), processorRef(p), progressBar(progressValue) {
  setSize(760, 420);

  titleLabel.setText("FL Beat Downloader (Companion Service)", juce::dontSendNotification);
  titleLabel.setFont(juce::FontOptions(18.0f));
  addAndMakeVisible(titleLabel);

  urlLabel.setText("Playlist/Song URL", juce::dontSendNotification);
  addAndMakeVisible(urlLabel);
  addAndMakeVisible(urlEditor);

  singleModeToggle.setButtonText("Single song mode");
  addAndMakeVisible(singleModeToggle);

  limitLabel.setText("Playlist limit (optional)", juce::dontSendNotification);
  addAndMakeVisible(limitLabel);
  limitEditor.setText("5");
  addAndMakeVisible(limitEditor);

  targetDirLabel.setText("Target directory", juce::dontSendNotification);
  addAndMakeVisible(targetDirLabel);
  targetDirEditor.setText((juce::File::getSpecialLocation(juce::File::userHomeDirectory).getChildFile("Downloads")).getFullPathName());
  addAndMakeVisible(targetDirEditor);

  chooseDirButton.setButtonText("Choose...");
  chooseDirButton.onClick = [this] {
    directoryChooser = std::make_unique<juce::FileChooser>("Select target folder");
    directoryChooser->launchAsync(
        juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectDirectories,
        [this](const juce::FileChooser& chooser) {
          auto selected = chooser.getResult();
          if (selected.exists()) {
            targetDirEditor.setText(selected.getFullPathName());
          }
        });
  };
  addAndMakeVisible(chooseDirButton);

  startButton.setButtonText("Start");
  startButton.onClick = [this] { submitJob(); };
  addAndMakeVisible(startButton);

  cancelButton.setButtonText("Cancel");
  cancelButton.onClick = [this] { cancelJob(); };
  cancelButton.setEnabled(false);
  addAndMakeVisible(cancelButton);

  serviceStartButton.setButtonText("Start Service");
  serviceStartButton.onClick = [this] { startService(); };
  addAndMakeVisible(serviceStartButton);

  serviceStopButton.setButtonText("Stop Service");
  serviceStopButton.onClick = [this] { stopService(); };
  addAndMakeVisible(serviceStopButton);

  statusLabel.setText("Idle", juce::dontSendNotification);
  statusLabel.setJustificationType(juce::Justification::centredLeft);
  addAndMakeVisible(statusLabel);
  addAndMakeVisible(progressBar);
  logBox.setMultiLine(true);
  logBox.setReadOnly(true);
  logBox.setScrollbarsShown(true);
  addAndMakeVisible(logBox);
  recentJobsLabel.setText("Recent jobs", juce::dontSendNotification);
  addAndMakeVisible(recentJobsLabel);
  recentJobsBox.setMultiLine(true);
  recentJobsBox.setReadOnly(true);
  recentJobsBox.setScrollbarsShown(true);
  addAndMakeVisible(recentJobsBox);

  ensureServiceRunning();
  startTimerHz(2);
}

FlBeatDownloaderEditor::~FlBeatDownloaderEditor() {
  stopTimer();
}

void FlBeatDownloaderEditor::paint(juce::Graphics& g) {
  g.fillAll(juce::Colour(0xff1d1d1d));
  g.setColour(juce::Colours::white);
}

void FlBeatDownloaderEditor::resized() {
  auto area = getLocalBounds().reduced(kPadding);
  titleLabel.setBounds(area.removeFromTop(30));
  area.removeFromTop(6);

  urlLabel.setBounds(area.removeFromTop(20));
  urlEditor.setBounds(area.removeFromTop(28));
  area.removeFromTop(6);

  singleModeToggle.setBounds(area.removeFromTop(24));
  limitLabel.setBounds(area.removeFromTop(20));
  limitEditor.setBounds(area.removeFromTop(24));
  area.removeFromTop(6);

  targetDirLabel.setBounds(area.removeFromTop(20));
  auto targetRow = area.removeFromTop(28);
  chooseDirButton.setBounds(targetRow.removeFromRight(90));
  targetRow.removeFromRight(6);
  targetDirEditor.setBounds(targetRow);
  area.removeFromTop(8);

  auto buttonRow = area.removeFromTop(28);
  startButton.setBounds(buttonRow.removeFromLeft(70));
  buttonRow.removeFromLeft(6);
  cancelButton.setBounds(buttonRow.removeFromLeft(70));
  buttonRow.removeFromLeft(6);
  serviceStartButton.setBounds(buttonRow.removeFromLeft(120));
  buttonRow.removeFromLeft(6);
  serviceStopButton.setBounds(buttonRow.removeFromLeft(110));
  area.removeFromTop(10);

  statusLabel.setBounds(area.removeFromTop(24));
  progressBar.setBounds(area.removeFromTop(24));
  area.removeFromTop(8);
  auto lower = area;
  auto left = lower.removeFromLeft(lower.proportionOfWidth(0.62f));
  logBox.setBounds(left);
  lower.removeFromLeft(8);
  recentJobsLabel.setBounds(lower.removeFromTop(20));
  recentJobsBox.setBounds(lower);
}

void FlBeatDownloaderEditor::timerCallback() {
  ++timerTicks;
  refreshUiFromState();
  pingService();
  if (activeJobId.isNotEmpty()) {
    fetchStatus();
  }
  if (serviceHealthy && (timerTicks % 8 == 0)) {
    fetchRecentJobs();
  }
}

void FlBeatDownloaderEditor::refreshUiFromState() {
  limitEditor.setEnabled(!singleModeToggle.getToggleState());
  serviceStartButton.setEnabled(!serviceHealthy);
  serviceStopButton.setEnabled(serviceHealthy);
  juce::String serviceState = serviceHealthy ? "Service: online" : "Service: offline";
  statusLabel.setText(serviceState + " | " + latestStatusText, juce::dontSendNotification);
}

void FlBeatDownloaderEditor::runRequestAsync(const juce::String& path, const juce::String& method, const juce::String& body) {
  if (postInFlight.exchange(true)) {
    return;
  }
  std::thread([this, path, method, body] {
    juce::URL url(serviceBaseUrl + path);
    int statusCode = 0;
    std::unique_ptr<juce::InputStream> stream(
        url.withPOSTData(body).createInputStream(
            juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inPostData)
                .withHttpRequestCmd(method)
                .withExtraHeaders("Content-Type: application/json\r\n")
                .withConnectionTimeoutMs(12000)
                .withStatusCode(&statusCode)));
    postInFlight = false;
    if (!stream) {
      juce::MessageManager::callAsync([this] {
        latestStatusText = "Service request failed";
        appendLog("Request failed");
      });
      return;
    }
    auto responseBody = stream->readEntireStreamAsString();
    juce::MessageManager::callAsync([this, responseBody, statusCode] {
      latestStatusText = "Request sent";
      appendLog("HTTP " + juce::String(statusCode) + " " + responseBody.substring(0, 160));
      if (responseBody.contains("job_id")) {
        auto json = juce::JSON::parse(responseBody);
        if (auto* obj = json.getDynamicObject()) {
          activeJobId = obj->getProperty("job_id").toString();
          cancelButton.setEnabled(true);
        }
      }
    });
  }).detach();
}

void FlBeatDownloaderEditor::runGetAsync(const juce::String& path, std::function<void(ApiResponse)> callback) {
  auto* guard = path.startsWith("/health") ? &healthInFlight : &statusInFlight;
  if (guard->exchange(true)) {
    return;
  }
  std::thread([this, path, callback = std::move(callback), guard] {
    ApiResponse out;
    juce::URL url(serviceBaseUrl + path);
    int statusCode = 0;
    std::unique_ptr<juce::InputStream> stream(
        url.createInputStream(
            juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
                .withHttpRequestCmd("GET")
                .withConnectionTimeoutMs(6000)
                .withStatusCode(&statusCode)));
    out.statusCode = statusCode;
    if (stream) {
      out.body = stream->readEntireStreamAsString();
    }
    *guard = false;
    juce::MessageManager::callAsync([callback, out] { callback(out); });
  }).detach();
}

void FlBeatDownloaderEditor::runGetJobsAsync(const juce::String& path, std::function<void(ApiResponse)> callback) {
  if (jobsInFlight.exchange(true)) {
    return;
  }
  std::thread([this, path, callback = std::move(callback)] {
    ApiResponse out;
    juce::URL url(serviceBaseUrl + path);
    int statusCode = 0;
    std::unique_ptr<juce::InputStream> stream(
        url.createInputStream(
            juce::URL::InputStreamOptions(juce::URL::ParameterHandling::inAddress)
                .withHttpRequestCmd("GET")
                .withConnectionTimeoutMs(7000)
                .withStatusCode(&statusCode)));
    out.statusCode = statusCode;
    if (stream) {
      out.body = stream->readEntireStreamAsString();
    }
    jobsInFlight = false;
    juce::MessageManager::callAsync([callback, out] { callback(out); });
  }).detach();
}

void FlBeatDownloaderEditor::submitJob() {
  if (urlEditor.getText().trim().isEmpty()) {
    latestStatusText = "Please enter a URL";
    return;
  }
  if (!serviceHealthy) {
    latestStatusText = "Service offline";
    ensureServiceRunning();
    return;
  }
  juce::DynamicObject::Ptr body = new juce::DynamicObject();
  body->setProperty("url", urlEditor.getText());
  body->setProperty("mode", singleModeToggle.getToggleState() ? "single" : "playlist");
  body->setProperty("target_dir", targetDirEditor.getText());
  body->setProperty("audio_format", "mp3");
  body->setProperty("keep_temp", false);
  if (!singleModeToggle.getToggleState()) {
    auto limitText = limitEditor.getText().trim();
    if (limitText.isNotEmpty()) {
      body->setProperty("limit", limitText.getIntValue());
    }
  }
  auto payload = juce::JSON::toString(juce::var(body.get()));
  latestStatusText = "Submitting job...";
  appendLog("Submitting new job");
  runRequestAsync("/jobs", "POST", payload);
}

void FlBeatDownloaderEditor::cancelJob() {
  if (activeJobId.isEmpty()) {
    return;
  }
  latestStatusText = "Cancelling...";
  appendLog("Cancel requested");
  runRequestAsync("/jobs/" + activeJobId + "/cancel", "POST", "{}");
}

void FlBeatDownloaderEditor::fetchStatus() {
  runGetAsync("/jobs/" + activeJobId, [this](ApiResponse rsp) {
    if (rsp.statusCode != 200) {
      return;
    }
    auto parsed = juce::JSON::parse(rsp.body);
    auto* obj = parsed.getDynamicObject();
    if (!obj) {
      return;
    }
    auto status = obj->getProperty("status").toString();
    auto progress = obj->getProperty("progress");
    juce::String message = status;
    if (auto* pObj = progress.getDynamicObject()) {
      auto stage = pObj->getProperty("stage").toString();
      if (stage.isNotEmpty()) {
        message = stage;
      } else if (pObj->hasProperty("message")) {
        message = pObj->getProperty("message").toString();
      }

      if (stage == "downloading") {
        progressValue = 0.25;
      } else if (stage == "processing" || stage == "processed") {
        progressValue = 0.70;
      } else if (stage == "skipped") {
        progressValue = 0.70;
      } else if (stage == "complete") {
        progressValue = 1.0;
      } else if (stage == "failed" || stage == "cancelled") {
        progressValue = 0.0;
      }
    }
    latestStatusText = message;
    if (message != lastLoggedStatus) {
      appendLog("Status: " + message);
      lastLoggedStatus = message;
    }
    if (status == "completed" || status == "failed" || status == "cancelled") {
      activeJobId = {};
      cancelButton.setEnabled(false);
      progressValue = (status == "completed") ? 1.0 : progressValue;
    }
    repaint();
  });
}

void FlBeatDownloaderEditor::fetchRecentJobs() {
  runGetJobsAsync("/jobs?limit=8", [this](ApiResponse rsp) {
    if (rsp.statusCode != 200) {
      return;
    }
    auto parsed = juce::JSON::parse(rsp.body);
    auto* obj = parsed.getDynamicObject();
    if (!obj) {
      return;
    }

    auto jobsVar = obj->getProperty("jobs");
    if (!jobsVar.isArray()) {
      return;
    }

    juce::String text;
    auto* arr = jobsVar.getArray();
    if (arr == nullptr || arr->isEmpty()) {
      text = "No jobs yet.";
    } else {
      for (const auto& v : *arr) {
        auto* jobObj = v.getDynamicObject();
        if (!jobObj) {
          continue;
        }
        auto id = jobObj->getProperty("id").toString();
        auto status = jobObj->getProperty("status").toString();
        auto reqVar = jobObj->getProperty("request");
        juce::String url;
        if (auto* reqObj = reqVar.getDynamicObject()) {
          url = reqObj->getProperty("url").toString();
        }
        if (url.length() > 52) {
          url = url.substring(0, 52) + "...";
        }
        text << status << " | " << id.substring(0, 8) << " | " << url << "\n";
      }
    }
    recentJobsBox.setText(text, false);
  });
}

void FlBeatDownloaderEditor::pingService() {
  runGetAsync("/health", [this](ApiResponse rsp) {
    serviceHealthy = (rsp.statusCode == 200);
    if (serviceHealthy != lastServiceHealthy) {
      appendLog(serviceHealthy ? "Companion service is online" : "Companion service is offline");
      lastServiceHealthy = serviceHealthy;
    }
    if (!serviceHealthy && activeJobId.isEmpty()) {
      latestStatusText = "Service offline";
    }
  });
}

void FlBeatDownloaderEditor::startService() {
  latestStatusText = "Starting companion service...";
  appendLog("Start Service clicked");
  ensureServiceRunning();
}

void FlBeatDownloaderEditor::stopService() {
  latestStatusText = "Stopping companion service...";
  appendLog("Stop Service clicked");
  juce::File root = resolveCompanionRoot();
  if (!isValidCompanionRoot(root)) {
    appendLog("Companion root not found. Set FL_VST_COMPANION_ROOT.");
    latestStatusText = "Companion root not found";
    return;
  }
  juce::String cmd = "cd \"" + root.getFullPathName() +
                     "\" && if [ -x ./scripts/stop_companion.sh ]; then ./scripts/stop_companion.sh >/tmp/fl_vst_companion.log 2>&1; fi";
  std::thread([cmd] { std::system(cmd.toRawUTF8()); }).detach();
}

void FlBeatDownloaderEditor::ensureServiceRunning() {
  juce::File root = resolveCompanionRoot();
  if (!isValidCompanionRoot(root)) {
    appendLog("Companion root not found. Set FL_VST_COMPANION_ROOT.");
    latestStatusText = "Companion root not found";
    return;
  }
  if (!root.getChildFile(".venv").isDirectory()) {
    appendLog("Missing .venv at root: " + root.getFullPathName());
    latestStatusText = "Missing .venv";
    return;
  }
  juce::String cmd = "cd \"" + root.getFullPathName() +
                     "\" && if [ -x ./scripts/run_companion.sh ]; then ./scripts/run_companion.sh >/tmp/fl_vst_companion.log 2>&1 & fi";
  std::thread([cmd] { std::system(cmd.toRawUTF8()); }).detach();
  appendLog("Attempted companion auto-start from: " + root.getFullPathName());
}

bool FlBeatDownloaderEditor::isValidCompanionRoot(const juce::File& root) const {
  return root.isDirectory() &&
         root.getChildFile("scripts").getChildFile("run_companion.sh").existsAsFile() &&
         root.getChildFile("service").getChildFile("app.py").existsAsFile();
}

juce::File FlBeatDownloaderEditor::resolveCompanionRoot() const {
  std::vector<juce::File> candidates;

  auto envRoot = juce::SystemStats::getEnvironmentVariable("FL_VST_COMPANION_ROOT", "");
  if (envRoot.isNotEmpty()) {
    candidates.emplace_back(envRoot);
  }

  auto cwd = juce::File::getCurrentWorkingDirectory();
  candidates.push_back(cwd);
  candidates.push_back(cwd.getParentDirectory());
  candidates.push_back(cwd.getParentDirectory().getParentDirectory());

  auto home = juce::File::getSpecialLocation(juce::File::userHomeDirectory);
  candidates.push_back(home.getChildFile("iCloud/2026/Coding-projects26/fl script"));
  candidates.push_back(home.getChildFile("Library/Mobile Documents/com~apple~CloudDocs/2026/Coding-projects26/fl script"));

  for (const auto& c : candidates) {
    if (isValidCompanionRoot(c)) {
      return c;
    }
  }
  return {};
}

void FlBeatDownloaderEditor::appendLog(const juce::String& line) {
  auto now = juce::Time::getCurrentTime().formatted("[%H:%M:%S] ");
  auto next = logBox.getText() + now + line + "\n";
  if (next.length() > 6000) {
    next = next.substring(next.length() - 6000);
  }
  logBox.setText(next, false);
  logBox.moveCaretToEnd();
}
