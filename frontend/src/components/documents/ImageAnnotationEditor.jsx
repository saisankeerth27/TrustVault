import { useEffect, useReducer, useRef, useState } from 'react'
import {
  ArrowUpRight,
  Circle,
  Eye,
  LoaderCircle,
  Minus,
  Pencil,
  Redo2,
  Save,
  ShieldCheck,
  Square,
  Type,
  Undo2,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { replaceExtension } from '@/lib/documents'
import { getApiErrorMessage } from '@/services/api'
import { createDocumentVersion } from '@/services/documents'

const MAX_CANVAS_DIMENSION = 1600

const TOOLS = [
  { value: 'pencil', label: 'Pencil', icon: Pencil },
  { value: 'line', label: 'Line', icon: Minus },
  { value: 'arrow', label: 'Arrow', icon: ArrowUpRight },
  { value: 'rectangle', label: 'Rectangle', icon: Square },
  { value: 'ellipse', label: 'Ellipse', icon: Circle },
  { value: 'text', label: 'Text', icon: Type },
]

function shapesReducer(state, action) {
  switch (action.type) {
    case 'add':
      return { shapes: [...state.shapes, action.shape], redo: [] }
    case 'undo': {
      if (state.shapes.length === 0) {
        return state
      }
      const last = state.shapes[state.shapes.length - 1]
      return {
        shapes: state.shapes.slice(0, -1),
        redo: [...state.redo, last],
      }
    }
    case 'redo': {
      if (state.redo.length === 0) {
        return state
      }
      const shape = state.redo[state.redo.length - 1]
      return {
        shapes: [...state.shapes, shape],
        redo: state.redo.slice(0, -1),
      }
    }
    default:
      return state
  }
}

function drawShape(context, shape) {
  context.save()
  context.strokeStyle = shape.color
  context.fillStyle = shape.color
  context.lineWidth = shape.width
  context.lineCap = 'round'
  context.lineJoin = 'round'

  if (shape.type === 'pencil') {
    const points = shape.points || []
    if (points.length === 1) {
      context.beginPath()
      context.arc(points[0].x, points[0].y, Math.max(1, shape.width / 2), 0, Math.PI * 2)
      context.fill()
    } else if (points.length > 1) {
      context.beginPath()
      context.moveTo(points[0].x, points[0].y)
      for (const point of points.slice(1)) {
        context.lineTo(point.x, point.y)
      }
      context.stroke()
    }
  } else if (shape.type === 'line' || shape.type === 'arrow') {
    context.beginPath()
    context.moveTo(shape.x1, shape.y1)
    context.lineTo(shape.x2, shape.y2)
    context.stroke()

    if (shape.type === 'arrow') {
      const angle = Math.atan2(shape.y2 - shape.y1, shape.x2 - shape.x1)
      const head = Math.max(10, shape.width * 3)
      context.beginPath()
      context.moveTo(shape.x2, shape.y2)
      context.lineTo(
        shape.x2 - head * Math.cos(angle - Math.PI / 7),
        shape.y2 - head * Math.sin(angle - Math.PI / 7),
      )
      context.moveTo(shape.x2, shape.y2)
      context.lineTo(
        shape.x2 - head * Math.cos(angle + Math.PI / 7),
        shape.y2 - head * Math.sin(angle + Math.PI / 7),
      )
      context.stroke()
    }
  } else if (shape.type === 'rectangle') {
    context.strokeRect(
      shape.x1,
      shape.y1,
      shape.x2 - shape.x1,
      shape.y2 - shape.y1,
    )
  } else if (shape.type === 'ellipse') {
    const centerX = (shape.x1 + shape.x2) / 2
    const centerY = (shape.y1 + shape.y2) / 2
    context.beginPath()
    context.ellipse(
      centerX,
      centerY,
      Math.abs(shape.x2 - shape.x1) / 2,
      Math.abs(shape.y2 - shape.y1) / 2,
      0,
      0,
      Math.PI * 2,
    )
    context.stroke()
  } else if (shape.type === 'text') {
    context.font = `600 ${shape.fontSize}px Inter, Arial, sans-serif`
    context.textBaseline = 'alphabetic'
    context.fillText(shape.text, shape.x, shape.y)
  }

  context.restore()
}

function drawScene(canvas, image, shapes, draft) {
  const context = canvas.getContext('2d')
  if (!context) {
    return
  }
  context.clearRect(0, 0, canvas.width, canvas.height)
  if (image) {
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
  }
  for (const shape of shapes) {
    drawShape(context, shape)
  }
  if (draft) {
    drawShape(context, draft)
  }
}

function canvasToBlob(canvas, mimeType) {
  return new Promise((resolve, reject) => {
    if (typeof canvas.toBlob !== 'function') {
      reject(new Error('This browser cannot export the edited image.'))
      return
    }
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob)
        } else {
          reject(new Error('The edited image could not be exported.'))
        }
      },
      mimeType,
      0.92,
    )
  })
}

/**
 * Canvas-based image annotation editor.
 *
 * Supports freehand pencil, lines, arrows, rectangles, ellipses, and text with
 * configurable colours and stroke width, plus undo/redo. Saving flattens the
 * annotations into the image and uploads it through the normal version API as a
 * new version. The server remains responsible for EDIT authorization.
 */
export function ImageAnnotationEditor({
  blob,
  documentRecord,
  currentVersion,
  onSaved,
  onConflict,
  onCancel,
}) {
  const canvasRef = useRef(null)
  const imageRef = useRef(null)
  const drawingRef = useRef(null)
  const [state, dispatch] = useReducer(shapesReducer, { shapes: [], redo: [] })
  const [draft, setDraft] = useState(null)
  const [tool, setTool] = useState('pencil')
  const [color, setColor] = useState('#e11d48')
  const [strokeWidth, setStrokeWidth] = useState(4)
  const [textValue, setTextValue] = useState('')
  const [changeSummary, setChangeSummary] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isStale, setIsStale] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [previewUrl, setPreviewUrl] = useState(null)

  const mimeType =
    documentRecord.mime_type === 'image/jpeg' ? 'image/jpeg' : 'image/png'
  const extension = mimeType === 'image/jpeg' ? 'jpg' : 'png'

  useEffect(() => {
    let active = true
    const objectUrl = URL.createObjectURL(blob)
    const image = new Image()

    setIsLoading(true)
    setLoadError(null)
    setPreviewUrl(null)

    image.onload = () => {
      if (!active) {
        return
      }
      const canvas = canvasRef.current
      if (!canvas) {
        return
      }
      const naturalWidth = image.naturalWidth || image.width || 800
      const naturalHeight = image.naturalHeight || image.height || 600
      const scale = Math.min(
        1,
        MAX_CANVAS_DIMENSION / Math.max(naturalWidth, naturalHeight),
      )
      canvas.width = Math.max(1, Math.round(naturalWidth * scale))
      canvas.height = Math.max(1, Math.round(naturalHeight * scale))
      imageRef.current = image
      setIsLoading(false)
    }
    image.onerror = () => {
      if (active) {
        setLoadError(new Error('The image could not be loaded for editing.'))
        setIsLoading(false)
      }
    }
    image.src = objectUrl

    return () => {
      active = false
      imageRef.current = null
      URL.revokeObjectURL(objectUrl)
    }
  }, [blob])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !imageRef.current) {
      return
    }
    drawScene(canvas, imageRef.current, state.shapes, draft)
  }, [state.shapes, draft, isLoading])

  function pointFromEvent(event) {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const scaleX = rect.width ? canvas.width / rect.width : 1
    const scaleY = rect.height ? canvas.height / rect.height : 1
    return {
      x: (event.clientX - rect.left) * scaleX,
      y: (event.clientY - rect.top) * scaleY,
    }
  }

  function handlePointerDown(event) {
    if (isLoading || isStale || !imageRef.current) {
      return
    }
    event.preventDefault()
    const point = pointFromEvent(event)

    if (tool === 'text') {
      const text = textValue.trim()
      if (!text) {
        return
      }
      dispatch({
        type: 'add',
        shape: {
          type: 'text',
          x: point.x,
          y: point.y,
          text,
          color,
          width: strokeWidth,
          fontSize: Math.max(18, strokeWidth * 5),
        },
      })
      return
    }

    const shape =
      tool === 'pencil'
        ? { type: 'pencil', points: [point], color, width: strokeWidth }
        : {
            type: tool,
            x1: point.x,
            y1: point.y,
            x2: point.x,
            y2: point.y,
            color,
            width: strokeWidth,
          }
    drawingRef.current = shape
    setDraft(shape)
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId)
    } catch {
      // Pointer capture is optional; drawing still works without it.
    }
  }

  function handlePointerMove(event) {
    const shape = drawingRef.current
    if (!shape) {
      return
    }
    const point = pointFromEvent(event)
    const nextShape =
      shape.type === 'pencil'
        ? { ...shape, points: [...shape.points, point] }
        : { ...shape, x2: point.x, y2: point.y }
    drawingRef.current = nextShape
    setDraft(nextShape)
  }

  function finishDrawing() {
    const shape = drawingRef.current
    if (!shape) {
      return
    }
    drawingRef.current = null
    setDraft(null)

    const hasSize =
      shape.type === 'pencil'
        ? shape.points.length > 1
        : Math.abs(shape.x2 - shape.x1) > 2 || Math.abs(shape.y2 - shape.y1) > 2
    if (hasSize) {
      dispatch({ type: 'add', shape })
    }
  }

  function handlePreview() {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }
    try {
      setPreviewUrl(canvas.toDataURL(mimeType))
    } catch {
      setPreviewUrl(null)
    }
    setShowPreview(true)
  }

  const canSave =
    Boolean(currentVersion) &&
    state.shapes.length > 0 &&
    !isLoading &&
    !loadError &&
    !isSaving &&
    !isStale

  async function handleSave() {
    if (!canSave || !canvasRef.current) {
      return
    }
    setSaveError(null)
    setIsSaving(true)
    try {
      const flattened = await canvasToBlob(canvasRef.current, mimeType)
      const file = new File(
        [flattened],
        replaceExtension(documentRecord.name, extension),
        { type: mimeType },
      )
      const result = await createDocumentVersion(
        documentRecord.id,
        file,
        currentVersion.version_number,
        changeSummary,
      )
      setShowPreview(false)
      onSaved(result)
    } catch (error) {
      if (error?.response?.status === 409) {
        setIsStale(true)
        onConflict?.()
      }
      setSaveError(
        error?.response?.status === 409
          ? `${getApiErrorMessage(error)} Close this editor and reopen it from the refreshed version before saving again.`
          : getApiErrorMessage(error),
      )
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Edit image</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Draw, add shapes, or place text on the image. Saving flattens your edits
            into a new immutable version.
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          <X className="size-4" aria-hidden="true" />
          Close
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadError ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {getApiErrorMessage(loadError)}
          </div>
        ) : null}

        {saveError ? (
          <div
            role="alert"
            className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {saveError}
          </div>
        ) : null}

        {!currentVersion ? (
          <div
            role="alert"
            className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          >
            Version history is unavailable, so this image cannot be saved safely.
            Refresh the page and try again.
          </div>
        ) : null}

        <div
          role="toolbar"
          aria-label="Image editing tools"
          className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2"
        >
          <div className="flex flex-wrap items-center gap-1">
            {TOOLS.map(({ value, label, icon: Icon }) => (
              <Button
                key={value}
                type="button"
                variant={tool === value ? 'default' : 'ghost'}
                size="sm"
                className="h-8 gap-1.5 px-2"
                aria-label={label}
                aria-pressed={tool === value}
                onClick={() => setTool(value)}
                disabled={isLoading || isStale}
              >
                <Icon className="size-4" aria-hidden="true" />
                <span className="hidden sm:inline">{label}</span>
              </Button>
            ))}
          </div>

          <span className="h-6 w-px bg-border" aria-hidden="true" />

          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Colour
            <input
              type="color"
              aria-label="Drawing colour"
              value={color}
              onChange={(event) => setColor(event.target.value)}
              disabled={isLoading || isStale}
              className="size-8 cursor-pointer rounded border bg-background p-0.5"
            />
          </label>

          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Width
            <input
              type="range"
              aria-label="Stroke width"
              min="1"
              max="24"
              value={strokeWidth}
              onChange={(event) => setStrokeWidth(Number(event.target.value))}
              disabled={isLoading || isStale}
              className="w-20"
            />
            <span className="w-6 text-right font-mono text-[11px]">
              {strokeWidth}
            </span>
          </label>

          <span className="h-6 w-px bg-border" aria-hidden="true" />

          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5 px-2"
            aria-label="Undo"
            onClick={() => dispatch({ type: 'undo' })}
            disabled={state.shapes.length === 0 || isSaving || isStale}
          >
            <Undo2 className="size-4" aria-hidden="true" />
            <span className="hidden sm:inline">Undo</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 gap-1.5 px-2"
            aria-label="Redo"
            onClick={() => dispatch({ type: 'redo' })}
            disabled={state.redo.length === 0 || isSaving || isStale}
          >
            <Redo2 className="size-4" aria-hidden="true" />
            <span className="hidden sm:inline">Redo</span>
          </Button>
        </div>

        {tool === 'text' ? (
          <div className="space-y-2">
            <label htmlFor="image-text-value" className="text-sm font-medium">
              Text to place
            </label>
            <input
              id="image-text-value"
              type="text"
              value={textValue}
              maxLength={200}
              onChange={(event) => setTextValue(event.target.value)}
              placeholder="Type text, then click the image"
              disabled={isLoading || isStale}
              className="flex h-10 w-full max-w-md rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        ) : null}

        <div className="relative overflow-auto rounded-lg border bg-muted/20 p-3">
          {isLoading ? (
            <div
              className="flex min-h-72 items-center justify-center gap-3 text-sm text-muted-foreground"
              aria-busy="true"
              aria-live="polite"
            >
              <LoaderCircle className="size-5 animate-spin" aria-hidden="true" />
              Loading image for editing...
            </div>
          ) : null}
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`Editable image: ${documentRecord.name}`}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={finishDrawing}
            onPointerLeave={finishDrawing}
            className="mx-auto max-h-[36rem] max-w-full touch-none rounded-sm bg-white shadow-sm"
          />
        </div>

        <div className="space-y-2">
          <label htmlFor="image-change-summary" className="text-sm font-medium">
            Change summary{' '}
            <span className="font-normal text-muted-foreground">(optional)</span>
          </label>
          <input
            id="image-change-summary"
            type="text"
            value={changeSummary}
            maxLength={500}
            onChange={(event) => setChangeSummary(event.target.value)}
            placeholder="Describe what changed in this version"
            disabled={isSaving || isStale}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={handlePreview}
            disabled={isLoading || !imageRef.current || isStale}
          >
            <Eye className="size-4" aria-hidden="true" />
            Preview image
          </Button>
          <Button type="button" onClick={handleSave} disabled={!canSave}>
            {isSaving ? (
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <Save className="size-4" aria-hidden="true" />
            )}
            {isSaving ? 'Saving version...' : 'Save new version'}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isSaving || isStale}
          >
            Cancel
          </Button>
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="size-3.5" aria-hidden="true" />
            The server validates and audits every new version.
          </span>
        </div>
      </CardContent>

      {showPreview ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Image preview"
        >
          <div className="max-h-full w-full max-w-3xl overflow-auto rounded-xl bg-background p-4 shadow-xl">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="font-semibold">Preview edited image</h2>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowPreview(false)}
                aria-label="Close image preview"
              >
                <X className="size-4" aria-hidden="true" />
              </Button>
            </div>
            {previewUrl ? (
              <img
                src={previewUrl}
                alt="Preview of the edited image"
                className="mx-auto max-h-[70vh] max-w-full rounded border object-contain"
              />
            ) : (
              <p className="rounded border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                A visual preview is unavailable in this browser. The canvas above
                still shows the edits that will be saved.
              </p>
            )}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowPreview(false)}
              >
                Back to editing
              </Button>
              <Button
                type="button"
                onClick={handleSave}
                disabled={!canSave}
              >
                {isSaving ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Save className="size-4" aria-hidden="true" />
                )}
                {isSaving ? 'Saving version...' : 'Save preview as version'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
