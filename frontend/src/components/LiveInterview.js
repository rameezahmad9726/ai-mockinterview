import React, { useState, useRef, useEffect } from 'react';
import { MicrophoneIcon, VideoCameraIcon, StopIcon, SpeakerWaveIcon, ChevronRightIcon, PlayIcon } from '@heroicons/react/24/outline';

const LiveInterview = ({ questions, sessionId }) => {
    const [isRecording, setIsRecording] = useState(false);
    const [currentQuestionIndex, setCurrentQuestionIndex] = useState(-1);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [recordedChunks, setRecordedChunks] = useState([]);
    const [stream, setStream] = useState(null);
    const [isFinished, setIsFinished] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [ttsUrls, setTtsUrls] = useState({});
    const [isPreloading, setIsPreloading] = useState(false);
    const [isFirstQuestionReady, setIsFirstQuestionReady] = useState(false);
    const [timeLeft, setTimeLeft] = useState(30); // 30 seconds for testing
    const QUESTION_TIME_LIMIT = 30;

    const audioContextRef = useRef(null);
    const mixedStreamRef = useRef(null);

    const videoRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const audioRef = useRef(new Audio());

    useEffect(() => {
        let timer;
        if (isRecording && !isSpeaking && currentQuestionIndex >= 0 && timeLeft > 0) {
            timer = setInterval(() => {
                setTimeLeft(prev => prev - 1);
            }, 1000);
        } else if (timeLeft === 0 && isRecording && !isSpeaking) {
            nextQuestion();
        }
        return () => clearInterval(timer);
    }, [isRecording, isSpeaking, currentQuestionIndex, timeLeft]);

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    useEffect(() => {
        if (questions && questions.length > 0 && sessionId) {
            preloadTtsSequentially();
        }
        return () => {
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
            if (audioContextRef.current) {
                audioContextRef.current.close();
            }
            // Cleanup blob URLs
            Object.values(ttsUrls).forEach(url => URL.revokeObjectURL(url));
        };
    }, [questions, sessionId]);

    const preloadTtsSequentially = async () => {
        setIsPreloading(true);
        try {
            const firstUrl = await fetchTts(questions[0].question, 0);
            if (firstUrl) {
                setTtsUrls(prev => ({ ...prev, 0: firstUrl }));
                setIsFirstQuestionReady(true);
            }
        } catch (err) {
            console.error("Failed to preload first question:", err);
            setIsFirstQuestionReady(true);
        }

        for (let i = 1; i < questions.length; i++) {
            try {
                const url = await fetchTts(questions[i].question, i);
                if (url) {
                    setTtsUrls(prev => ({ ...prev, [i]: url }));
                }
            } catch (err) {
                console.error(`Failed to preload TTS for Q${i}:`, err);
            }
        }
        setIsPreloading(false);
    };

    const fetchTts = async (text, index) => {
        try {
            const response = await fetch('http://localhost:8000/generate-tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: text,
                    session_id: sessionId,
                    index: index
                })
            });
            const data = await response.json();

            // 🔥 NEW: Actually download the bytes now so playback is instant later
            const audioRes = await fetch(data.url);
            const blob = await audioRes.blob();
            return URL.createObjectURL(blob);
        } catch (err) {
            console.error("fetchTts error:", err);
            return null;
        }
    };

    const startCamera = async () => {
        try {
            const userStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            setStream(userStream);
            if (videoRef.current) {
                videoRef.current.srcObject = userStream;
            }
        } catch (err) {
            console.error("Error accessing camera:", err);
            alert("Camera access denied or not available.");
        }
    };

    const [isAudioInitialized, setIsAudioInitialized] = useState(false);
    const aiSourceRef = useRef(null);
    const destinationRef = useRef(null);

    const initializeAudioSystem = async () => {
        if (isAudioInitialized) return;

        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            const audioContext = new AudioContextClass();
            audioContextRef.current = audioContext;

            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }

            const micSource = audioContext.createMediaStreamSource(stream);

            // Crucial: crossOrigin MUST be set before src
            audioRef.current.crossOrigin = "anonymous";

            const aiSource = audioContext.createMediaElementSource(audioRef.current);
            aiSourceRef.current = aiSource;

            const destination = audioContext.createMediaStreamDestination();
            destinationRef.current = destination;

            micSource.connect(destination);
            aiSource.connect(destination);
            aiSource.connect(audioContext.destination);

            setIsAudioInitialized(true);
            return destination.stream;
        } catch (err) {
            console.error("Audio init failed:", err);
            return null;
        }
    };

    const startInterview = async () => {
        if (!stream || isRecording) return;

        const mixedAudioStream = await initializeAudioSystem();
        if (!mixedAudioStream) {
            alert("Could not initialize audio mixing. Check mic permissions.");
            return;
        }

        const videoTrack = stream.getVideoTracks()[0];
        const mixedAudioTrack = mixedAudioStream.getAudioTracks()[0];

        const combinedStream = new MediaStream([videoTrack, mixedAudioTrack]);
        mixedStreamRef.current = combinedStream;

        setIsRecording(true);
        setRecordedChunks([]);

        const mediaRecorder = new MediaRecorder(combinedStream, { mimeType: 'video/webm' });
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                setRecordedChunks(prev => [...prev, e.data]);
            }
        };

        mediaRecorder.start(1000);
        nextQuestion();
    };

    const nextQuestion = async () => {
        const nextIndex = currentQuestionIndex + 1;
        if (nextIndex >= questions.length) {
            finishInterview();
            return;
        }

        // 🔥 IMMEDIATE UI UPDATE: Change question text and reset timer instantly
        setCurrentQuestionIndex(nextIndex);
        setTimeLeft(QUESTION_TIME_LIMIT);
        setIsSpeaking(true); // Don't let timer run while preparing audio

        // Stop current audio if playing
        audioRef.current.pause();
        audioRef.current.currentTime = 0;

        const playAudio = (url) => {
            audioRef.current.src = url;
            setIsSpeaking(true);

            // 🔥 INSTANT PLAY: Since it's a blob, we don't need to wait for buffering
            const playPromise = audioRef.current.play();
            if (playPromise !== undefined) {
                playPromise.catch(err => {
                    if (err.name !== 'AbortError') {
                        console.error("Audio play error:", err);
                        setIsSpeaking(false);
                    }
                });
            }

            audioRef.current.onended = () => {
                setIsSpeaking(false);
            };
        };

        if (ttsUrls[nextIndex]) {
            playAudio(ttsUrls[nextIndex]);
        } else {
            // Fallback: fetch it now if not already preloaded
            try {
                const response = await fetch('http://localhost:8000/generate-tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: questions[nextIndex].question,
                        session_id: sessionId,
                        index: nextIndex
                    })
                });
                const data = await response.json();
                if (data.url) {
                    playAudio(data.url);
                } else {
                    setIsSpeaking(false); // Start timer if no audio
                }
            } catch (err) {
                console.error("Delayed TTS generation failed:", err);
                setIsSpeaking(false); // Start timer on error
            }
        }
    };

    const finishInterview = () => {
        setIsRecording(false);
        if (mediaRecorderRef.current) {
            mediaRecorderRef.current.stop();
        }
        setIsFinished(true);

        // Cleanup streams
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            setStream(null);
        }
        if (mixedStreamRef.current) {
            mixedStreamRef.current.getTracks().forEach(track => track.stop());
        }
        if (audioContextRef.current) {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }
    };

    const [analysisProgress, setAnalysisProgress] = useState(0);
    const [analysisStatus, setAnalysisStatus] = useState("");
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [analysisResult, setAnalysisResult] = useState(null);

    const pollAnalysisStatus = async (sid) => {
        try {
            const response = await fetch(`http://localhost:8000/analysis-status/${sid}`);
            const data = await response.json();

            if (data.status === "error") {
                alert("Analysis failed: " + data.message);
                setIsAnalyzing(false);
                return;
            }

            setAnalysisProgress(data.progress);
            setAnalysisStatus(data.status);

            if (data.progress === 100 && data.result) {
                // Analysis complete!
                const report = data.result.report || {};
                setAnalysisResult({
                    ...(report || {}),
                    report_json_path: data.result.report_json_path,
                    report_html_path: data.result.report_html_path,
                });
                setIsAnalyzing(false);
            } else {
                // Continue polling
                setTimeout(() => pollAnalysisStatus(sid), 2000);
            }
        } catch (err) {
            console.error("Polling error:", err);
            setTimeout(() => pollAnalysisStatus(sid), 5000);
        }
    };

    const handleUpload = async () => {
        setIsUploading(true);
        const blob = new Blob(recordedChunks, { type: 'video/webm' });
        const file = new File([blob], `interview_${sessionId}.webm`, { type: 'video/webm' });

        const formData = new FormData();
        formData.append('file', file);
        formData.append('questions', JSON.stringify(questions.map(q => q.question)));

        try {
            const response = await fetch('http://localhost:8000/analyze', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();

            if (data.status === "started") {
                setIsAnalyzing(true);
                pollAnalysisStatus(data.session_id);
            } else {
                const errorMsg = data.detail || data.message || "Unknown error";
                alert(`Failed to start analysis: ${errorMsg}`);
            }
        } catch (err) {
            console.error("Upload failed:", err);
            alert("Failed to upload video. Please ensure the backend server is running.");
        } finally {
            setIsUploading(false);
        }
    };

    const downloadVideo = () => {
        const blob = new Blob(recordedChunks, { type: 'video/webm' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = `interview_${sessionId}.webm`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
    };

    if (analysisResult) {
        // Show the results component if analysis is done
        const ResultsDisplay = require('./ResultsDisplay').default;
        return (
            <div className="animate-fade-in">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-3xl font-bold text-white">Interview Analysis Result</h2>
                    <button
                        onClick={() => window.location.reload()}
                        className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-all"
                    >
                        Back to Home
                    </button>
                </div>
                <ResultsDisplay results={analysisResult} />
            </div>
        );
    }

    return (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 shadow-xl animate-fade-in max-w-4xl mx-auto">
            <h2 className="text-2xl font-bold text-white mb-6 flex items-center">
                <VideoCameraIcon className="h-8 w-8 mr-3 text-red-500" />
                Live AI Interview
            </h2>

            {!isFinished ? (
                <div className="space-y-6">
                    {/* Camera Preview */}
                    <div className="relative aspect-video bg-slate-900 rounded-lg overflow-hidden border-2 border-slate-700">
                        <video
                            ref={videoRef}
                            autoPlay
                            muted
                            playsInline
                            className="w-full h-full object-cover"
                        />
                        {!stream && (
                            <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80">
                                <button
                                    onClick={startCamera}
                                    className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-full font-bold transition-all shadow-lg"
                                >
                                    Enable Camera & Mic
                                </button>
                            </div>
                        )}
                        {isRecording && (
                            <div className="absolute top-4 left-4 flex items-center bg-red-600/80 text-white px-3 py-1 rounded-full text-sm font-bold animate-pulse">
                                <div className="w-2 h-2 bg-white rounded-full mr-2"></div>
                                LIVE RECORDING
                            </div>
                        )}
                    </div>

                    {/* Question Display */}
                    {isRecording && currentQuestionIndex >= 0 && (
                        <div className="bg-slate-900/80 border border-indigo-500/30 rounded-lg p-6 animate-fade-in relative overflow-hidden">
                            {/* Visual Progress Bar */}
                            <div
                                className={`absolute top-0 left-0 h-1 transition-all duration-1000 ${timeLeft < 15 ? 'bg-red-500' : 'bg-indigo-500'}`}
                                style={{ width: `${(timeLeft / QUESTION_TIME_LIMIT) * 100}%` }}
                            ></div>

                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center text-indigo-400 text-sm font-bold uppercase tracking-widest">
                                    <SpeakerWaveIcon className={`h-5 w-5 mr-2 ${isSpeaking ? 'animate-bounce' : ''}`} />
                                    {isSpeaking ? 'AI IS SPEAKING...' : 'YOUR TURN TO ANSWER'}
                                </div>
                                {!isSpeaking && (
                                    <div className={`flex items-center font-mono text-lg font-bold ${timeLeft < 15 ? 'text-red-500 animate-pulse' : 'text-slate-300'}`}>
                                        <StopIcon className="h-5 w-5 mr-1" />
                                        {formatTime(timeLeft)}
                                    </div>
                                )}
                            </div>
                            <p className="text-xl text-white font-medium leading-relaxed">
                                {questions[currentQuestionIndex].question}
                            </p>

                            <div className="mt-8 flex justify-end">
                                <button
                                    onClick={nextQuestion}
                                    className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg font-bold flex items-center transition-all"
                                >
                                    {currentQuestionIndex === questions.length - 1 ? 'Finish Interview' : 'Next Question'}
                                    <ChevronRightIcon className="h-5 w-5 ml-2" />
                                </button>
                            </div>
                        </div>
                    )}

                    {!isRecording && stream && (
                        <div className="flex justify-center">
                            <button
                                onClick={startInterview}
                                disabled={!isFirstQuestionReady}
                                className={`px-10 py-4 rounded-full font-bold text-lg flex items-center shadow-xl transition-all hover:scale-105 text-white
                                    ${!isFirstQuestionReady ? 'bg-slate-700 cursor-wait' : 'bg-red-600 hover:bg-red-700 shadow-red-900/20'}`}
                            >
                                {!isFirstQuestionReady ? (
                                    <>
                                        <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                        </svg>
                                        Preparing Interview...
                                    </>
                                ) : (
                                    <>
                                        <PlayIcon className="h-6 w-6 mr-2" />
                                        Start Interview
                                    </>
                                )}
                            </button>
                        </div>
                    )}

                    {isFirstQuestionReady && isPreloading && (
                        <p className="text-center text-slate-500 text-xs animate-pulse">
                            (AI is still loading later questions in background...)
                        </p>
                    )}
                </div>
            ) : (
                <div className="text-center py-12 space-y-8 animate-fade-in">
                    {isAnalyzing ? (
                        <div className="space-y-8 max-w-md mx-auto">
                            <div className="relative w-24 h-24 mx-auto">
                                <div className="absolute inset-0 border-4 border-slate-700 rounded-full"></div>
                                <div
                                    className="absolute inset-0 border-4 border-indigo-500 rounded-full border-t-transparent animate-spin"
                                ></div>
                                <div className="absolute inset-0 flex items-center justify-center font-bold text-white">
                                    {analysisProgress}%
                                </div>
                            </div>

                            <div>
                                <h3 className="text-2xl font-bold text-white mb-2">Analyzing Interview...</h3>
                                <p className="text-slate-400 animate-pulse">{analysisStatus}</p>
                            </div>

                            <div className="bg-slate-700 h-2 rounded-full overflow-hidden">
                                <div
                                    className="bg-indigo-500 h-full transition-all duration-500"
                                    style={{ width: `${analysisProgress}%` }}
                                ></div>
                            </div>

                            <p className="text-slate-500 text-sm">
                                Please don't close this tab while we process your video.
                            </p>
                        </div>
                    ) : (
                        <>
                            <div className="bg-green-500/20 text-green-400 p-6 rounded-full w-24 h-24 mx-auto flex items-center justify-center border-2 border-green-500/30">
                                <ChevronRightIcon className="h-12 w-12" />
                            </div>
                            <div>
                                <h3 className="text-3xl font-bold text-white mb-2">Interview Completed!</h3>
                                <p className="text-slate-400">Great job! Your interview has been recorded and is ready for analysis.</p>
                            </div>

                            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                                <button
                                    onClick={handleUpload}
                                    disabled={isUploading}
                                    className="bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-3 rounded-full font-bold min-w-[200px] flex items-center justify-center transition-all disabled:opacity-50"
                                >
                                    {isUploading ? "Uploading..." : "Upload for Analysis"}
                                </button>
                                <button
                                    onClick={downloadVideo}
                                    className="border border-slate-600 hover:bg-slate-700 text-white px-8 py-3 rounded-full font-bold min-w-[200px] transition-all"
                                >
                                    Download Recording
                                </button>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
};

export default LiveInterview;
