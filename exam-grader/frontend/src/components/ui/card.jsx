import { clsx } from 'clsx'

export function Card({ children, className, ...props }) {
  return (
    <div
      className={clsx('bg-white rounded-xl shadow-sm border border-gray-200', className)}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardHeader({ children, className }) {
  return (
    <div className={clsx('px-6 py-5 border-b border-gray-100', className)}>
      {children}
    </div>
  )
}

export function CardBody({ children, className }) {
  return (
    <div className={clsx('px-6 py-5', className)}>
      {children}
    </div>
  )
}

export function CardFooter({ children, className }) {
  return (
    <div className={clsx('px-6 py-4 border-t border-gray-100 bg-gray-50 rounded-b-xl', className)}>
      {children}
    </div>
  )
}
