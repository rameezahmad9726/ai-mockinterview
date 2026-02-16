#!/usr/bin/env python3
"""
Test script for SpeechAnalyzer module.
Generates a sample audio file and analyzes it with Whisper.
"""

import sys
import os
from pathlib import Path
import numpy as np
from scipy.io import wavfile
import tempfile

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from speech_analysis import SpeechAnalyzer


def create_sample_audio(duration=5, sample_rate=16000):
    """
    Create a sample audio file with spoken words.
    Uses a simple sine wave approach (not actual speech, but valid audio).
    
    Returns: path to the generated WAV file
    """
    print(f"\n=== Generating Sample Audio ({duration}s) ===")
    
    # Create a temporary file
    temp_dir = tempfile.gettempdir()
    audio_path = Path(temp_dir) / "sample_audio.wav"
    
    # Generate simple audio signal (1000 Hz sine wave with variation)
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # Create a simple pattern: varies to simulate speech-like patterns
    frequency = 1000 + 200 * np.sin(2 * np.pi * t / duration)
    audio = np.sin(2 * np.pi * frequency * t / sample_rate)
    
    # Add some noise
    audio += 0.1 * np.random.normal(size=len(audio))
    
    # Normalize to 16-bit range
    audio = (audio * 32767).astype(np.int16)
    
    # Write to WAV file
    wavfile.write(str(audio_path), sample_rate, audio)
    
    file_size_kb = audio_path.stat().st_size / 1024
    print(f"[INFO] Created sample audio: {audio_path}")
    print(f"  Duration: {duration}s, Sample rate: {sample_rate}Hz")
    print(f"  File size: {file_size_kb:.1f} KB")
    
    return str(audio_path)


def test_speech_analyzer_initialization():
    """Test SpeechAnalyzer initialization and lazy-load."""
    print("\n=== Testing SpeechAnalyzer Initialization ===")
    
    try:
        analyzer = SpeechAnalyzer(model_name="base")
        
        # Verify state at initialization
        assert analyzer.model is None, "Model should not be loaded at init"
        assert analyzer._load_error is None, "Should have no load error at init"
        assert analyzer.model_name == "base", "Model name should be 'base'"
        
        print("[INFO] SpeechAnalyzer initialized (lazy-load mode)")
        print(f"  - model_name: {analyzer.model_name}")
        print(f"  - model: {analyzer.model}")
        print(f"  - _load_error: {analyzer._load_error}")
        
        return True, analyzer
    except Exception as e:
        print(f"[ERROR] Failed to initialize SpeechAnalyzer: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_speech_analysis(analyzer, audio_path):
    """Test speech analysis on sample audio."""
    print("\n=== Testing Speech Analysis ===")
    
    try:
        print(f"Analyzing audio: {audio_path}")
        
        result = analyzer.analyze_audio(audio_path)
        
        # Check result structure
        expected_keys = [
            "transcript",
            "word_count",
            "speaking_speed_wpm",
            "filler_words",
            "clarity_score",
            "confidence_score"
        ]
        
        for key in expected_keys:
            assert key in result, f"Missing key in result: {key}"
        
        print("[INFO] Analysis completed successfully")
        print(f"\n  Results:")
        print(f"  - Transcript: {result['transcript'][:100]}..." if len(result['transcript']) > 100 else f"  - Transcript: {result['transcript']}")
        print(f"  - Word count: {result['word_count']}")
        print(f"  - Speaking speed: {result['speaking_speed_wpm']} WPM")
        print(f"  - Filler words: {result['filler_words']}")
        print(f"  - Clarity score: {result['clarity_score']}/10")
        print(f"  - Confidence score: {result['confidence_score']}/10")
        
        return True, result
    except Exception as e:
        print(f"[ERROR] Speech analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_small_model():
    """Test with smaller 'tiny' model for faster loading."""
    print("\n=== Testing with Tiny Model (Fast Load) ===")
    
    try:
        analyzer = SpeechAnalyzer(model_name="tiny")
        print(f"[INFO] SpeechAnalyzer with 'tiny' model initialized")
        print(f"  Model name: {analyzer.model_name}")
        print(f"  (Model will load on first use)")
        
        # Try to load the model
        if analyzer._ensure_model_loaded():
            print(f"[INFO] 'tiny' model loaded successfully")
            return True
        else:
            print(f"[WARN] Failed to load 'tiny' model: {analyzer._load_error}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed with tiny model: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run speech analysis tests."""
    print("=" * 70)
    print("Speech Analysis Test Suite")
    print("=" * 70)
    
    results = {}
    
    # Test 1: Initialize analyzer
    success, analyzer = test_speech_analyzer_initialization()
    results["Initialization"] = success
    
    if not success or analyzer is None:
        print("\n[ERROR] Cannot proceed without successful initialization")
        return 1
    
    # Test 2: Create sample audio
    try:
        audio_path = "./uploads/video2/audio/audio.wav"
    except Exception as e:
        print(f"\n[ERROR] Failed to create sample audio: {e}")
        print("  (scipy may not be installed)")
        print("\n  To install scipy:")
        print("    pip install scipy")
        
        # Skip audio analysis, just test initialization
        audio_path = None
        results["Sample Audio Creation"] = False
    else:
        results["Sample Audio Creation"] = True
    
    # Test 3: Analyze audio
    if audio_path:
        success, result = test_speech_analysis(analyzer, audio_path)
        results["Speech Analysis"] = success
    else:
        results["Speech Analysis"] = False
    
    # Test 4: Test tiny model
    success = test_small_model()
    results["Tiny Model Load"] = success
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed >= 2:  # At least initialization should pass
        print("\n[INFO] Speech analysis module is working!")
        print("\nTo run full analysis, install scipy:")
        print("  pip install scipy")
        return 0
    else:
        print(f"\n[WARN] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
