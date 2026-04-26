import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import './App.css';
import { AuthProvider } from './context/AuthContext';
import DemoApp from './DemoApp';
import Login from './components/hr/Login';
import HRLayout from './components/hr/HRLayout';
import Dashboard from './components/hr/Dashboard';
import JobsList from './components/hr/JobsList';
import JobCreate from './components/hr/JobCreate';
import JobDetail from './components/hr/JobDetail';
import CompareView from './components/hr/CompareView';
import CandidateDetail from './components/hr/CandidateDetail';
import CandidateInterview from './pages/CandidateInterview';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="/login" element={<Login />} />
          <Route path="/demo" element={<DemoApp />} />
          <Route path="/interview/:token" element={<CandidateInterview />} />

          <Route path="/hr" element={<HRLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="jobs" element={<JobsList />} />
            <Route path="jobs/new" element={<JobCreate />} />
            <Route path="jobs/:jobId" element={<JobDetail />} />
            <Route path="jobs/:jobId/compare" element={<CompareView />} />
            <Route path="sessions/:externalId" element={<CandidateDetail />} />
          </Route>

          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
