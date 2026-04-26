import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { API_BASE, apiFetch } from '../api';
import LiveInterview from '../components/LiveInterview';
import SystemCheck from '../components/candidate/SystemCheck';
import ResumeUpload from '../components/candidate/ResumeUpload';

// Wizard stages
const STAGE = {
  LOADING: 'loading',
  INVALID: 'invalid',
  WELCOME: 'welcome',
  SYSCHECK: 'syscheck',
  RESUME: 'resume',
  INTERVIEW: 'interview',
  COMPLETE: 'complete',
};

function Shell({ title, subtitle, children }) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-slate-100">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10">
        <header className="mb-8">
          <h1 className="text-2xl font-bold">{title}</h1>
          {subtitle ? <p className="text-slate-400 text-sm mt-1">{subtitle}</p> : null}
        </header>
        <div className="bg-slate-800/40 border border-slate-700 rounded-2xl p-6 sm:p-8 shadow-xl">
          {children}
        </div>
      </div>
    </div>
  );
}

export default function CandidateInterview() {
  const { token } = useParams();

  const [stage, setStage] = useState(STAGE.LOADING);
  const [session, setSession] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const info = await apiFetch(`/api/interview/${token}`, { auth: false });
        if (!active) return;
        setSession(info);
        // Decide initial stage based on what's already done.
        if (info.status === 'submitted' || info.status === 'analyzing' || info.status === 'scored') {
          setStage(STAGE.COMPLETE);
        } else if (info.has_resume && info.questions && info.questions.length > 0) {
          setStage(STAGE.WELCOME);
        } else {
          setStage(STAGE.WELCOME);
        }
      } catch (e) {
        if (!active) return;
        setError(typeof e.detail === 'string' ? e.detail : 'Invalid or expired link');
        setStage(STAGE.INVALID);
      }
    })();
    return () => { active = false; };
  }, [token]);

  // --- LiveInterview adapters ---
  const customUpload = async ({ blob, answerWindows }) => {
    const fd = new FormData();
    const file = new File([blob], `interview_${session.session_external_id}.webm`, { type: 'video/webm' });
    fd.append('file', file);
    if (answerWindows && answerWindows.length) {
      fd.append('answer_windows', JSON.stringify(answerWindows));
    }
    const res = await fetch(`${API_BASE}/api/interview/${token}/submit`, {
      method: 'POST',
      body: fd,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Upload failed (${res.status})`);
    }
    return res.json();
  };

  const onSubmitted = () => {
    setStage(STAGE.COMPLETE);
  };

  // --- Stage renderers ---
  if (stage === STAGE.LOADING) {
    return (
      <Shell title="Preparing your interview...">
        <p className="text-slate-400">Validating your link.</p>
      </Shell>
    );
  }

  if (stage === STAGE.INVALID) {
    return (
      <Shell title="Link not available">
        <p className="text-slate-300">{error || 'This interview link is invalid or has expired.'}</p>
        <p className="text-slate-500 text-sm mt-4">
          If you believe this is a mistake, reply to the invitation email to request a new link.
        </p>
      </Shell>
    );
  }

  if (stage === STAGE.WELCOME) {
    const expires = new Date(session.expires_at).toLocaleString();
    return (
      <Shell
        title={`${session.company || 'Interveux'} · ${session.job_title}`}
        subtitle="Video interview"
      >
        <div className="space-y-5">
          <p className="text-slate-200">
            Welcome! You've been invited to complete a short video interview for the
            <strong> {session.job_title}</strong> role.
          </p>
          <ul className="list-disc list-inside text-sm text-slate-300 space-y-1">
            <li>{session.num_questions} questions, about {session.seconds_per_answer} seconds per answer.</li>
            <li>You'll need camera + microphone access in a quiet, well-lit room.</li>
            <li>Your responses are analyzed automatically. The hiring team will follow up by email.</li>
            <li>This link expires <strong>{expires}</strong>.</li>
          </ul>

          <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-4 text-xs text-slate-400">
            By continuing, you consent to being recorded and to having your responses analyzed
            by automated systems as part of the hiring process.
          </div>

          <button
            onClick={async () => {
              try {
                await apiFetch(`/api/interview/${token}/consent`, { method: 'POST', auth: false });
              } catch (_) { /* consent is best-effort */ }
              setStage(STAGE.SYSCHECK);
            }}
            className="w-full py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold"
          >
            I consent — let's begin
          </button>
        </div>
      </Shell>
    );
  }

  if (stage === STAGE.SYSCHECK) {
    return (
      <Shell title={`${session.job_title} · Step 1 of 3`} subtitle="Camera + microphone check">
        <SystemCheck
          onReady={() => setStage(session.has_resume ? STAGE.INTERVIEW : STAGE.RESUME)}
        />
      </Shell>
    );
  }

  if (stage === STAGE.RESUME) {
    return (
      <Shell title={`${session.job_title} · Step 2 of 3`} subtitle="Resume upload">
        <ResumeUpload
          token={token}
          onDone={(info) => {
            setSession(info);
            setStage(STAGE.INTERVIEW);
          }}
        />
      </Shell>
    );
  }

  if (stage === STAGE.INTERVIEW) {
    return (
      <Shell title={`${session.job_title} · Step 3 of 3`} subtitle="Interview">
        <LiveInterview
          questions={session.questions || []}
          sessionId={session.session_external_id}
          resumeContext={null /* already on server */}
          customUpload={customUpload}
          onAnalysisDone={onSubmitted}
          autoUploadOnFinish
          waitForAnalysis={false}
          hidePostInterviewActions
        />
      </Shell>
    );
  }

  // COMPLETE
  return (
    <Shell title="Thank you!" subtitle={session?.job_title}>
      <div className="text-center space-y-4 py-6">
        <div className="mx-auto w-16 h-16 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
          <svg className="w-8 h-8 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p className="text-slate-200">
          Your interview was submitted successfully. Our hiring team will review and follow up with you by email.
        </p>
        <p className="text-slate-500 text-sm">You can safely close this tab.</p>
      </div>
    </Shell>
  );
}
