#include <cstring>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "keyfinder.h"

namespace {

struct WavData {
  uint16_t channels;
  uint32_t sampleRate;
  uint16_t bitsPerSample;
  uint16_t audioFormat;
  std::vector<uint8_t> pcm;
};

uint32_t readLE32(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) |
         (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) |
         (static_cast<uint32_t>(p[3]) << 24);
}

uint16_t readLE16(const uint8_t* p) {
  return static_cast<uint16_t>(p[0]) | (static_cast<uint16_t>(p[1]) << 8);
}

WavData loadWav(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("Cannot open file: " + path);
  }

  std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  if (bytes.size() < 44) {
    throw std::runtime_error("WAV file too small");
  }
  if (std::string(reinterpret_cast<char*>(&bytes[0]), 4) != "RIFF" ||
      std::string(reinterpret_cast<char*>(&bytes[8]), 4) != "WAVE") {
    throw std::runtime_error("Not a RIFF/WAVE file");
  }

  uint16_t channels = 0;
  uint32_t sampleRate = 0;
  uint16_t bitsPerSample = 0;
  uint16_t audioFormat = 0;
  std::vector<uint8_t> pcm;

  size_t pos = 12;
  while (pos + 8 <= bytes.size()) {
    const std::string chunkId(reinterpret_cast<char*>(&bytes[pos]), 4);
    const uint32_t chunkSize = readLE32(&bytes[pos + 4]);
    pos += 8;
    if (pos + chunkSize > bytes.size()) {
      throw std::runtime_error("Corrupt WAV chunk size");
    }

    if (chunkId == "fmt ") {
      if (chunkSize < 16) {
        throw std::runtime_error("Invalid fmt chunk");
      }
      audioFormat = readLE16(&bytes[pos + 0]);
      channels = readLE16(&bytes[pos + 2]);
      sampleRate = readLE32(&bytes[pos + 4]);
      bitsPerSample = readLE16(&bytes[pos + 14]);
    } else if (chunkId == "data") {
      pcm.assign(bytes.begin() + static_cast<long>(pos), bytes.begin() + static_cast<long>(pos + chunkSize));
    }

    pos += chunkSize;
    if (chunkSize % 2 == 1 && pos < bytes.size()) {
      pos += 1;
    }
  }

  if (channels == 0 || sampleRate == 0 || bitsPerSample == 0 || pcm.empty()) {
    throw std::runtime_error("Missing WAV metadata or PCM data");
  }
  if (!(audioFormat == 1 || audioFormat == 3)) {
    throw std::runtime_error("Unsupported WAV format (only PCM16/PCM32f supported)");
  }
  if (!((audioFormat == 1 && bitsPerSample == 16) || (audioFormat == 3 && bitsPerSample == 32))) {
    throw std::runtime_error("Unsupported WAV bit depth");
  }

  return {channels, sampleRate, bitsPerSample, audioFormat, std::move(pcm)};
}

double sampleAt(const WavData& wav, size_t frame, size_t channel) {
  const size_t bytesPerSample = wav.bitsPerSample / 8;
  const size_t sampleIndex = frame * wav.channels + channel;
  const size_t offset = sampleIndex * bytesPerSample;
  if (offset + bytesPerSample > wav.pcm.size()) {
    return 0.0;
  }

  if (wav.audioFormat == 1 && wav.bitsPerSample == 16) {
    const int16_t raw = static_cast<int16_t>(readLE16(&wav.pcm[offset]));
    return static_cast<double>(raw) / 32768.0;
  }

  float value = 0.0f;
  std::memcpy(&value, &wav.pcm[offset], sizeof(float));
  return static_cast<double>(value);
}

std::string keyToString(KeyFinder::key_t key) {
  switch (key) {
    case KeyFinder::A_MAJOR: return "Amaj";
    case KeyFinder::A_MINOR: return "Am";
    case KeyFinder::B_FLAT_MAJOR: return "Bbmaj";
    case KeyFinder::B_FLAT_MINOR: return "Bbm";
    case KeyFinder::B_MAJOR: return "Bmaj";
    case KeyFinder::B_MINOR: return "Bm";
    case KeyFinder::C_MAJOR: return "Cmaj";
    case KeyFinder::C_MINOR: return "Cm";
    case KeyFinder::D_FLAT_MAJOR: return "Dbmaj";
    case KeyFinder::D_FLAT_MINOR: return "Dbm";
    case KeyFinder::D_MAJOR: return "Dmaj";
    case KeyFinder::D_MINOR: return "Dm";
    case KeyFinder::E_FLAT_MAJOR: return "Ebmaj";
    case KeyFinder::E_FLAT_MINOR: return "Ebm";
    case KeyFinder::E_MAJOR: return "Emaj";
    case KeyFinder::E_MINOR: return "Em";
    case KeyFinder::F_MAJOR: return "Fmaj";
    case KeyFinder::F_MINOR: return "Fm";
    case KeyFinder::G_FLAT_MAJOR: return "Gbmaj";
    case KeyFinder::G_FLAT_MINOR: return "Gbm";
    case KeyFinder::G_MAJOR: return "Gmaj";
    case KeyFinder::G_MINOR: return "Gm";
    case KeyFinder::A_FLAT_MAJOR: return "Abmaj";
    case KeyFinder::A_FLAT_MINOR: return "Abm";
    case KeyFinder::SILENCE: return "SILENCE";
    default: return "UNKNOWN";
  }
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "Usage: keyfinder_cli <input.wav>\n";
    return 2;
  }

  try {
    WavData wav = loadWav(argv[1]);

    const size_t bytesPerSample = wav.bitsPerSample / 8;
    const size_t frameCount = wav.pcm.size() / (bytesPerSample * wav.channels);
    if (frameCount == 0) {
      throw std::runtime_error("No audio frames found");
    }

    KeyFinder::AudioData audio;
    audio.setChannels(wav.channels);
    audio.setFrameRate(wav.sampleRate);
    audio.addToFrameCount(static_cast<unsigned int>(frameCount));

    for (size_t frame = 0; frame < frameCount; ++frame) {
      for (size_t channel = 0; channel < wav.channels; ++channel) {
        audio.setSampleByFrame(
          static_cast<unsigned int>(frame),
          static_cast<unsigned int>(channel),
          sampleAt(wav, frame, channel)
        );
      }
    }

    KeyFinder::KeyFinder finder;
    const KeyFinder::key_t detected = finder.keyOfAudio(audio);
    std::cout << keyToString(detected) << "\n";
    return 0;
  } catch (const std::exception& ex) {
    std::cerr << ex.what() << "\n";
    return 1;
  }
}
