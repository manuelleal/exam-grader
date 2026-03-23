import { useRef, useState } from 'react'
import { clsx } from 'clsx'
import { UploadCloud, X, FileImage, File } from 'lucide-react'

export function FileUpload({
  accept = 'image/*',
  multiple = false,
  files = [],
  onChange,
  maxFiles,
  label = 'Drop files here or click to browse',
  sublabel,
  disabled = false,
}) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [typeError, setTypeError] = useState(null)

  const isAccepted = (file) => {
    if (!accept || accept === '*') return true
    return accept.split(',').some((a) => {
      const t = a.trim()
      if (t.endsWith('/*')) return file.type.startsWith(t.slice(0, -1))
      return file.type === t || file.name.toLowerCase().endsWith(t.replace('*.', '.'))
    })
  }

  const addFiles = (incoming) => {
    const list = Array.from(incoming)
    const invalid = list.filter((f) => !isAccepted(f))
    if (invalid.length) {
      const exts = invalid.map((f) => f.name.split('.').pop().toUpperCase()).join(', ')
      setTypeError(`${exts} not supported. Please upload image or PDF files (.jpg, .png, .webp, .pdf).`)
      return
    }
    setTypeError(null)
    const combined = multiple ? [...files, ...list] : list
    const capped = maxFiles ? combined.slice(0, maxFiles) : combined
    onChange?.(capped)
  }

  const removeFile = (index) => {
    setTypeError(null)
    const next = files.filter((_, i) => i !== index)
    onChange?.(next)
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    if (!disabled) addFiles(e.dataTransfer.files)
  }

  const onDragOver = (e) => {
    e.preventDefault()
    if (!disabled) setDragging(true)
  }

  const onDragLeave = () => setDragging(false)

  const onInputChange = (e) => {
    if (e.target.files?.length) addFiles(e.target.files)
    e.target.value = ''
  }

  const isImage = (file) => file.type.startsWith('image/')

  return (
    <div className="space-y-3">
      <div
        onClick={() => !disabled && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={clsx(
          'border-2 border-dashed rounded-xl p-8 text-center transition-colors',
          dragging
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50',
          disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          className="hidden"
          onChange={onInputChange}
          disabled={disabled}
        />
        <UploadCloud className={clsx('w-10 h-10 mx-auto mb-3', dragging ? 'text-blue-500' : 'text-gray-400')} />
        <p className="text-sm font-medium text-gray-700">{label}</p>
        {sublabel && <p className="text-xs text-gray-400 mt-1">{sublabel}</p>}
        {maxFiles && (
          <p className="text-xs text-gray-400 mt-1">
            {files.length}/{maxFiles} files selected
          </p>
        )}
      </div>

      {typeError && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2 text-sm">
          <span className="shrink-0">⚠</span>
          <span>{typeError}</span>
        </div>
      )}

      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((file, i) => (
            <li
              key={i}
              className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded-lg border border-gray-200"
            >
              {isImage(file) ? (
                <FileImage className="w-4 h-4 text-blue-500 shrink-0" />
              ) : (
                <File className="w-4 h-4 text-gray-500 shrink-0" />
              )}
              <span className="text-sm text-gray-700 truncate flex-1">{file.name}</span>
              <span className="text-xs text-gray-400 shrink-0">
                {(file.size / 1024).toFixed(0)} KB
              </span>
              {!disabled && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); removeFile(i) }}
                  className="text-gray-400 hover:text-red-500 transition-colors shrink-0"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
