import React from 'react';
import { Link, NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

function NavItem({ to, children, end = false }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
          isActive
            ? 'bg-indigo-500/20 text-indigo-300'
            : 'text-slate-300 hover:bg-slate-800 hover:text-white'
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function HRLayout() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-slate-300">
        Loading...
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;

  const onLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <header className="bg-slate-950/80 backdrop-blur border-b border-slate-800 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center gap-6">
          <Link to="/hr" className="text-lg font-bold text-white">
            Interveux <span className="text-indigo-400">HR</span>
          </Link>
          <nav className="flex gap-1">
            <NavItem to="/hr" end>Dashboard</NavItem>
            <NavItem to="/hr/jobs">Jobs</NavItem>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-slate-400">{user.email}</span>
            <button
              onClick={onLogout}
              className="px-3 py-1.5 rounded-md border border-slate-700 text-slate-300 hover:bg-slate-800"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}
