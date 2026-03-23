import { Link, useNavigate } from 'react-router-dom'
import { GraduationCap, LayoutDashboard, LogOut } from 'lucide-react'
import useAuthStore from '../store/authStore'

export default function Navbar() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <nav className="bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/dashboard" className="flex items-center gap-2 text-blue-600 font-bold text-lg">
            <GraduationCap className="w-6 h-6" />
            <span>ExamGrader</span>
          </Link>

          {/* Nav links */}
          <div className="hidden sm:flex items-center gap-1">
            <Link
              to="/dashboard"
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 rounded-lg hover:bg-gray-100 hover:text-gray-900 transition-colors"
            >
              <LayoutDashboard className="w-4 h-4" />
              Dashboard
            </Link>
          </div>

          {/* User + logout */}
          <div className="flex items-center gap-3">
            {user && (
              <span className="hidden sm:block text-sm text-gray-500">
                {user.name || user.email}
              </span>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 rounded-lg hover:bg-red-50 hover:text-red-600 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
      </div>
    </nav>
  )
}
