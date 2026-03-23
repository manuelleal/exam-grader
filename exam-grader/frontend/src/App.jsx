import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import NewTemplate from './pages/NewTemplate'
import NewSession from './pages/NewSession'
import SessionResults from './pages/SessionResults'
import ExamDetail from './pages/ExamDetail'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Protected routes */}
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/templates/new" element={<NewTemplate />} />
          <Route path="/sessions/new" element={<NewSession />} />
          <Route path="/sessions/:id" element={<SessionResults />} />
          <Route path="/exams/:id" element={<ExamDetail />} />
        </Route>

        {/* Redirect root → login (or dashboard if already auth) */}
        <Route path="/" element={<Navigate to="/login" replace />} />

        {/* 404 fallback */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
