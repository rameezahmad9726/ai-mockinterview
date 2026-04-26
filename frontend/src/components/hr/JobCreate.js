import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../../api';

function Field({ label, children, hint }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium text-slate-300 mb-1">{label}</span>
      {children}
      {hint ? <span className="block text-xs text-slate-500 mt-1">{hint}</span> : null}
    </label>
  );
}

const inputCls =
  'w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500';

export default function JobCreate() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    title: '',
    department: '',
    seniority: '',
    jd_text: '',
    required_skills: '',
    required_certifications: '',
    num_questions: 5,
    seconds_per_answer: 90,
    allow_retakes: false,
    link_expiry_hours: 72,
    auto_reject_threshold: 50,
    shortlist_threshold: 80,
    calendly_url: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        required_skills: form.required_skills
          .split(',').map((s) => s.trim()).filter(Boolean),
        required_certifications: form.required_certifications
          .split(',').map((s) => s.trim()).filter(Boolean),
      };
      const job = await apiFetch('/api/hr/jobs', { method: 'POST', body: payload });
      navigate(`/hr/jobs/${job.id}`);
    } catch (e) {
      setError(typeof e.detail === 'string' ? e.detail : 'Failed to create job');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-white mb-6">Create a new job</h1>

      <form onSubmit={onSubmit} className="space-y-5 bg-slate-800/40 border border-slate-700 rounded-xl p-6">
        <Field label="Title">
          <input required className={inputCls} value={form.title} onChange={(e) => set('title', e.target.value)} placeholder="Backend Engineer" />
        </Field>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <Field label="Department">
            <input className={inputCls} value={form.department} onChange={(e) => set('department', e.target.value)} placeholder="Engineering" />
          </Field>
          <Field label="Seniority">
            <input className={inputCls} value={form.seniority} onChange={(e) => set('seniority', e.target.value)} placeholder="Mid" />
          </Field>
        </div>

        <Field label="Job description" hint="Used to tailor interview questions.">
          <textarea className={inputCls} rows={4} value={form.jd_text} onChange={(e) => set('jd_text', e.target.value)} />
        </Field>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <Field label="Required skills" hint="Comma-separated">
            <input className={inputCls} value={form.required_skills} onChange={(e) => set('required_skills', e.target.value)} placeholder="Python, FastAPI, PostgreSQL" />
          </Field>
          <Field label="Required certifications" hint="Comma-separated">
            <input className={inputCls} value={form.required_certifications} onChange={(e) => set('required_certifications', e.target.value)} placeholder="AWS SAA" />
          </Field>
        </div>

        <h3 className="text-sm font-semibold text-slate-300 pt-2 border-t border-slate-700">Interview configuration</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Field label="# questions">
            <input type="number" min={1} max={20} className={inputCls} value={form.num_questions} onChange={(e) => set('num_questions', parseInt(e.target.value || 0, 10))} />
          </Field>
          <Field label="Seconds per answer">
            <input type="number" min={10} max={600} className={inputCls} value={form.seconds_per_answer} onChange={(e) => set('seconds_per_answer', parseInt(e.target.value || 0, 10))} />
          </Field>
          <Field label="Link expiry (hours)">
            <input type="number" min={1} max={720} className={inputCls} value={form.link_expiry_hours} onChange={(e) => set('link_expiry_hours', parseInt(e.target.value || 0, 10))} />
          </Field>
          <Field label="Allow retakes">
            <select className={inputCls} value={form.allow_retakes ? 'yes' : 'no'} onChange={(e) => set('allow_retakes', e.target.value === 'yes')}>
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </select>
          </Field>
        </div>

        <h3 className="text-sm font-semibold text-slate-300 pt-2 border-t border-slate-700">Decisioning (0–100)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <Field label="Auto-reject below" hint="Candidates scoring below this are auto-rejected.">
            <input type="number" min={0} max={100} className={inputCls} value={form.auto_reject_threshold} onChange={(e) => set('auto_reject_threshold', parseInt(e.target.value || 0, 10))} />
          </Field>
          <Field label="Shortlist at/above" hint="Candidates scoring this high are auto-shortlisted.">
            <input type="number" min={0} max={100} className={inputCls} value={form.shortlist_threshold} onChange={(e) => set('shortlist_threshold', parseInt(e.target.value || 0, 10))} />
          </Field>
        </div>

        <Field label="Calendly link (optional)" hint="If set, shortlisted candidates get this self-booking link in their shortlist email.">
          <input type="url" className={inputCls} value={form.calendly_url} onChange={(e) => set('calendly_url', e.target.value)} placeholder="https://calendly.com/you/30min" />
        </Field>

        {error && (
          <div className="text-sm text-red-300 bg-red-950/50 border border-red-800 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 text-white font-semibold"
          >
            {submitting ? 'Creating...' : 'Create job'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-5 py-2 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
