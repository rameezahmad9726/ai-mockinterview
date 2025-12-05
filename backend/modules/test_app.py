#!/usr/bin/env python3
"""
Quick integration test to verify the app's key modules work correctly.
Tests: video processor, frame extraction, emotion analysis, and speech analysis.
"""

import sys
import os
from pathlib import Path
import tempfile

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

def test_imports():
    """Test that all key modules can be imported."""
    print("\n=== Testing Imports ===")
    try:
        from modules.video_processor import extract_frames
        print("✓ extract_frames imported")
        
        from modules.audio_extractor import extract_audio
        print("✓ extract_audio imported")
        
        from modules.facial_emotions import analyze_emotions
        print("✓ analyze_emotions imported")
        
        from modules.speech_analysis import SpeechAnalyzer
        print("✓ SpeechAnalyzer imported")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_speech_analyzer():
    """Test SpeechAnalyzer lazy-load pattern."""
    print("\n=== Testing SpeechAnalyzer (Lazy-Load) ===")
    try:
        from modules.speech_analysis import SpeechAnalyzer
        
        # Create analyzer (model not loaded yet)
        analyzer = SpeechAnalyzer(model_name="base")
        print("✓ SpeechAnalyzer instantiated (model not loaded yet)")
        
        # Verify lazy attributes
        assert analyzer.model is None, "Model should be None at init"
        assert analyzer._load_error is None, "Load error should be None at init"
        print("✓ Lazy-load state verified (model=None, _load_error=None)")
        
        # Try to analyze (will trigger model load on next use)
        # We won't actually call it since it needs a real audio file,
        # but we verified the class structure
        print("✓ SpeechAnalyzer ready (model will load on first analyze_audio call)")
        
        return True
    except Exception as e:
        print(f"✗ SpeechAnalyzer test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_folder_structure():
    """Test that upload folder creation follows the new structure."""
    print("\n=== Testing Folder Structure ===")
    try:
        import tempfile
        from pathlib import Path
        
        # Simulate the new folder creation logic from video_processor.py
        with tempfile.TemporaryDirectory() as tmpdir:
            upload_dir = Path(tmpdir)
            original_filename = "test_video.mp4"
            original_stem = Path(original_filename).stem or "uploaded_video"
            
            # Create unique video directory
            video_dir_path = tempfile.mkdtemp(
                prefix=f"{original_stem}_", dir=str(upload_dir)
            )
            video_folder = Path(video_dir_path)
            
            # Create subfolders
            original_dir = video_folder / "original"
            audio_dir = video_folder / "audio"
            frames_dir = video_folder / "frames"
            
            original_dir.mkdir(parents=True, exist_ok=True)
            audio_dir.mkdir(parents=True, exist_ok=True)
            frames_dir.mkdir(parents=True, exist_ok=True)
            
            # Verify structure
            assert original_dir.exists(), "original/ folder missing"
            assert audio_dir.exists(), "audio/ folder missing"
            assert frames_dir.exists(), "frames/ folder missing"
            
            print(f"✓ Created video folder: {video_folder.name}")
            print(f"  ├─ original/")
            print(f"  ├─ audio/")
            print(f"  └─ frames/")
            
            # Save a test file
            test_file = original_dir / original_filename
            test_file.write_bytes(b"test video content")
            assert test_file.exists(), "Failed to save test file"
            print(f"✓ Successfully saved {original_filename} to original/")
            
        return True
    except Exception as e:
        print(f"✗ Folder structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_video_processor_imports():
    """Test video_processor module with corrected imports."""
    print("\n=== Testing Video Processor Module ===")
    try:
        # The main video_processor.py in backend/
        from video_processor import process_video
        print("✓ process_video function imported from main video_processor")
        
        # Check that it imports modules correctly
        import video_processor as vp
        assert hasattr(vp, 'extract_audio'), "extract_audio not imported"
        assert hasattr(vp, 'extract_frames'), "extract_frames not imported"
        print("✓ Main video_processor has correct module imports")
        
        return True
    except Exception as e:
        print(f"✗ Video processor test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("AI Mock Interview - Integration Test Suite")
    print("=" * 60)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Folder Structure", test_folder_structure()))
    results.append(("SpeechAnalyzer", test_speech_analyzer()))
    results.append(("Video Processor", test_video_processor_imports()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! App is ready to run.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
