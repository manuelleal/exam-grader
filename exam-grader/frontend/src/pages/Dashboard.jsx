import { GraduationCap, FileText, PlayCircle, BarChart3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import Navbar from '../components/Navbar'
import { Card, CardBody } from '../components/ui/card'
import useAuthStore from '../store/authStore'

const quickLinks = [
  {
    label: 'New Template',
    description: 'Create a grading rubric',
    href: '/templates/new',
    icon: FileText,
    color: 'bg-blue-50 text-blue-600',
  },
  {
    label: 'New Session',
    description: 'Start grading exams',
    href: '/sessions/new',
    icon: PlayCircle,
    color: 'bg-green-50 text-green-600',
  },
  {
    label: 'View Results',
    description: 'Check graded sessions',
    href: '/sessions',
    icon: BarChart3,
    color: 'bg-purple-50 text-purple-600',
  },
]

export default function Dashboard() {
  const user = useAuthStore((s) => s.user)

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">
            Welcome, {user?.name || 'Teacher'} 👋
          </h1>
          <p className="text-gray-500 mt-1">What would you like to do today?</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          {quickLinks.map(({ label, description, href, icon: Icon, color }) => (
            <Link key={href} to={href}>
              <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
                <CardBody>
                  <div className={`inline-flex p-3 rounded-xl ${color} mb-4`}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <h2 className="font-semibold text-gray-900">{label}</h2>
                  <p className="text-sm text-gray-500 mt-1">{description}</p>
                </CardBody>
              </Card>
            </Link>
          ))}
        </div>

        <div className="mt-10 text-center text-sm text-gray-400 flex flex-col items-center gap-1">
          <GraduationCap className="w-8 h-8 text-gray-300" />
          <span>More features coming soon — this is Part 1 of the frontend.</span>
        </div>
      </main>
    </div>
  )
}
