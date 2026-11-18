import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'

/** Drag-and-drop or click-to-browse for a single DICOM file. */
export function UploadDropzone({ onFile, disabled, progress }) {
  const inputRef = useRef(null)
  const [dragging, setDragging] = useState(false)

  function pick(files) {
    const file = files?.[0]
    if (file && !disabled) onFile(file)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        pick(e.dataTransfer.files)
      }}
      className={`flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-6 py-8 text-center transition-colors ${
        disabled
          ? 'cursor-not-allowed border-border bg-muted/40'
          : dragging
            ? 'cursor-copy border-primary bg-primary/5'
            : 'cursor-pointer border-border bg-surface hover:border-primary hover:bg-muted/40'
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".dcm,application/dicom"
        className="hidden"
        onChange={(e) => {
          pick(e.target.files)
          e.target.value = ''
        }}
      />
      <Upload size={28} strokeWidth={1.6} className="text-muted-foreground" />
      {progress === null || progress === undefined ? (
        <>
          <p className="text-sm font-semibold text-foreground">Drop an OCT volume here, or click to browse</p>
          <p className="text-xs text-muted-foreground">Heidelberg Spectralis OCT volume (DICOM, .dcm)</p>
        </>
      ) : (
        <div className="w-full max-w-sm">
          <p className="mb-2 text-sm font-semibold text-foreground">
            {progress < 1 ? `Uploading… ${Math.round(progress * 100)}%` : 'Checking the file…'}
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        </div>
      )}
    </div>
  )
}
