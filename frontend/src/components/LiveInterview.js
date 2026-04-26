import React, { useState, useRef, useEffect } from 'react';
import { MicrophoneIcon, VideoCameraIcon, StopIcon, SpeakerWaveIcon, ChevronRightIcon, PlayIcon } from '@heroicons/react/24/outline';

/**
 * Props:
 *   questions, sessionId, resumeContext — as before
 *   customUpload?:  async ({ blob, answerWindows, questions }) => {}
 *                   When provided, replaces the default POST /analyze flow.
 *                   Should throw on failure. Return value is passed to customPoll (if any).
 *   customPoll?:    async () => { progress, status, done, result?, error? }
 *                   When provided, replaces the default /analysis-status polling.
 *   onAnalysisDone?: (result) => void — called once when analysis finishes.
 *                    Suppresses the built-in ResultsDisplay swap so the host page
 *                    can render its own completion screen.
 *   autoUploadOnFinish?: boolean — automatically uploads as soon as recording ends.
 *   waitForAnalysis?: boolean — if false, considers flow complete after upload starts.
 *   hidePostInterviewActions?: boolean — hides upload/download controls after recording.
 */
const LiveInterview = ({
    questions,
    sessionId,
    resumeContext,
    customUpload,
    customPoll,
    onAnalysisDone,
    autoUploadOnFinish = false,
    waitForAnalysis = true,
    hidePostInterviewActions = false,
}) => {
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
    const QUESTION_TIME_LIMIT = 60;
    const [timeLeft, setTimeLeft] = useState(QUESTION_TIME_LIMIT);

    const audioContextRef = useRef(null);
    const mixedStreamRef = useRef(null);

    const videoRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const audioRef = useRef(new Audio());

    // Per-question answering windows — start when the TTS finishes playing
    // (candidate begins speaking), end when the question is advanced/skipped
    // or the recording finishes. Sent to the backend so eye-contact flags
    // outside these windows (i.e. while the candidate is reading/listening)
    // are suppressed.
    const recordingStartRef = useRef(null);           // ms timestamp
    const currentAnswerRef = useRef(null);            // { idx, start_sec } | null
    const answerWindowsRef = useRef([]);              // [{question_idx, start_sec, end_sec}]

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
            preloadTtsParallel();
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

    const preloadTtsParallel = async () => {
        setIsPreloading(true);
        try {
            const qList = questions.map((q, i) => ({
                question: typeof q === 'object' ? q.question : q,
                index: i
            }));

            // Prioritize Q0: generate it first so user can start quickly
            const q0 = qList[0];
            const q0Res = await fetch('http://localhost:8000/generate-tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: q0.question,
                    session_id: sessionId,
                    index: 0
                })
            });
            const q0Data = await q0Res.json();
            if (q0Data?.url) {
                try {
                    const blobRes = await fetch(q0Data.url);
                    const blob = await blobRes.blob();
                    const blobUrl = URL.createObjectURL(blob);
                    setTtsUrls(prev => ({ ...prev, 0: blobUrl }));
                    setIsFirstQuestionReady(true);
                } catch (e) {
                    console.error('Failed to fetch Q0 TTS:', e);
                    setIsFirstQuestionReady(true);
                }
            } else {
                setIsFirstQuestionReady(true);
            }

            // Generate remaining questions in background (don't block)
            if (qList.length > 1) {
                fetch('http://localhost:8000/generate-tts-batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: sessionId,
                        questions: qList.slice(1)
                    })
                })
                    .then(res => res.json())
                    .then(data => {
                        if (!data.urls?.length) return;
                        return Promise.all(data.urls.map(async (u) => {
                            if (!u.url) return { index: u.index, blobUrl: null };
                            try {
                                const res = await fetch(u.url);
                                const blob = await res.blob();
                                return { index: u.index, blobUrl: URL.createObjectURL(blob) };
                            } catch (e) {
                                console.error(`Failed to fetch TTS for Q${u.index}:`, e);
                                return { index: u.index, blobUrl: null };
                            }
                        }));
                    })
                    .then(results => {
                        if (!results) return;
                        const nextUrls = {};
                        results.forEach(({ index, blobUrl }) => {
                            if (blobUrl) nextUrls[index] = blobUrl;
                        });
                        setTtsUrls(prev => ({ ...prev, ...nextUrls }));
                    })
                    .catch(err => console.error('Background TTS batch failed:', err));
            }
        } catch (err) {
            console.error("Failed to preload TTS:", err);
            setIsFirstQuestionReady(true);
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
        recordingStartRef.current = Date.now();
        currentAnswerRef.current = null;
        answerWindowsRef.current = [];
        nextQuestion();
    };

    const _nowSec = () => {
        if (!recordingStartRef.current) return 0;
        return Math.max(0, (Date.now() - recordingStartRef.current) / 1000);
    };

    const beginAnswerWindow = (idx) => {
        if (!recordingStartRef.current) return;
        currentAnswerRef.current = { idx, start_sec: _nowSec() };
    };

    const closeCurrentAnswerWindow = () => {
        const cur = currentAnswerRef.current;
        if (cur && recordingStartRef.current) {
            const end_sec = _nowSec();
            if (end_sec > cur.start_sec) {
                answerWindowsRef.current.push({
                    question_idx: cur.idx,
                    start_sec: cur.start_sec,
                    end_sec: end_sec,
                });
            }
        }
        currentAnswerRef.current = null;
    };

    const nextQuestion = async () => {
        // Close the previous question's answering window (if any) before moving on.
        closeCurrentAnswerWindow();

        const nextIndex = currentQuestionIndex + 1;
        if (nextIndex >= questions.length) {
            finishInterview();
            return;
        }

        setCurrentQuestionIndex(nextIndex);
        setTimeLeft(QUESTION_TIME_LIMIT);
        setIsSpeaking(true); // Don't let timer run while preparing audio

        audioRef.current.pause();
        audioRef.current.currentTime = 0;

        const playAudio = (url) => {
            audioRef.current.src = url;
            setIsSpeaking(true);

            const playPromise = audioRef.current.play();
            if (playPromise !== undefined) {
                playPromise.catch(err => {
                    if (err.name !== 'AbortError') {
                        console.error("Audio play error:", err);
                        setIsSpeaking(false);
                        beginAnswerWindow(nextIndex);
                    }
                });
            }

            audioRef.current.onended = () => {
                setIsSpeaking(false);
                beginAnswerWindow(nextIndex);
            };
        };

        if (ttsUrls[nextIndex]) {
            playAudio(ttsUrls[nextIndex]);
        } else {
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
                    setIsSpeaking(false);
                    beginAnswerWindow(nextIndex);
                }
            } catch (err) {
                console.error("Delayed TTS generation failed:", err);
                setIsSpeaking(false);
                beginAnswerWindow(nextIndex);
            }
        }
    };

    const finishInterview = () => {
        // Close the last in-progress answer window before stopping the recorder.
        closeCurrentAnswerWindow();
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
    const autoUploadStartedRef = useRef(false);

    const pollAnalysisStatus = async (sid) => {
        // Candidate-flow override: host page drives status via customPoll and
        // owns the completion screen, so this component just reports progress.
        if (customPoll) {
            try {
                const data = await customPoll();
                setAnalysisProgress(data.progress || 0);
                setAnalysisStatus(data.status || "");
                if (data.error) {
                    alert("Analysis failed: " + data.error);
                    setIsAnalyzing(false);
                    return;
                }
                if (data.done) {
                    setIsAnalyzing(false);
                    if (onAnalysisDone) onAnalysisDone(data.result || null);
                    return;
                }
                setTimeout(() => pollAnalysisStatus(sid), 2000);
            } catch (err) {
                console.error("Custom poll error:", err);
                setTimeout(() => pollAnalysisStatus(sid), 5000);
            }
            return;
        }

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
                if (onAnalysisDone) onAnalysisDone(data.result || null);
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
        if (!recordedChunks.length) {
            alert("No interview recording found to upload.");
            return;
        }
        setIsUploading(true);
        const blob = new Blob(recordedChunks, { type: 'video/webm' });
        const answerWindows = answerWindowsRef.current || [];

        // Candidate-flow override: host page is responsible for the upload
        // (it knows the candidate token) and for kicking off polling.
        if (customUpload) {
            try {
                await customUpload({ blob, answerWindows, questions });
                if (waitForAnalysis) {
                    setIsAnalyzing(true);
                    pollAnalysisStatus(sessionId);
                } else if (onAnalysisDone) {
                    onAnalysisDone(null);
                }
            } catch (err) {
                console.error("Custom upload failed:", err);
                alert("Failed to upload: " + (err?.message || err));
            } finally {
                setIsUploading(false);
            }
            return;
        }

        const file = new File([blob], `interview_${sessionId}.webm`, { type: 'video/webm' });

        const formData = new FormData();
        formData.append('file', file);
        formData.append('questions', JSON.stringify(
            questions.map(q => typeof q === 'object' ? q : { question: q, type: 'General' })
        ));
        if (resumeContext) {
            formData.append('resume_context', JSON.stringify({
                domain: resumeContext.domain,
                certifications: resumeContext.certifications || [],
                key_skills: resumeContext.key_skills || [],
            }));
            if (resumeContext.resume_session_id) {
                formData.append('resume_session_id', resumeContext.resume_session_id);
            }
        }
        if (answerWindows.length > 0) {
            formData.append('answer_windows', JSON.stringify(answerWindows));
        }

        try {
            const response = await fetch('http://localhost:8000/analyze', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();

            if (data.status === "started") {
                if (waitForAnalysis) {
                    setIsAnalyzing(true);
                    pollAnalysisStatus(data.session_id);
                } else if (onAnalysisDone) {
                    onAnalysisDone(null);
                }
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

    useEffect(() => {
        if (!autoUploadOnFinish || !isFinished || isUploading || isAnalyzing) return;
        if (autoUploadStartedRef.current) return;
        if (!recordedChunks.length) return;
        autoUploadStartedRef.current = true;
        handleUpload();
    }, [autoUploadOnFinish, isFinished, isUploading, isAnalyzing, recordedChunks]);

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
                                        {isPreloading ? 'Generating first question audio...' : 'Preparing Interview...'}
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

                            {!hidePostInterviewActions && (
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
                            )}
                            {hidePostInterviewActions && (
                                <p className="text-slate-500 text-sm">
                                    Uploading your interview in the background...
                                </p>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
};

export default LiveInterview;
