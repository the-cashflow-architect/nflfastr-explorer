import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface Position {
  top: number
  left: number
  placement: 'top' | 'bottom'
}

/**
 * Hover/focus tooltip rendered into a portal at document.body.
 *
 * Table headers, filter labels, and stat tiles all live inside scrolling
 * containers (`overflow-auto`) or panels with `overflow-hidden` corners.
 * A tooltip positioned `absolute` relative to its trigger gets silently
 * clipped by the nearest such ancestor — that's why hovers "don't show
 * appropriately". Rendering into a portal with `position: fixed`, computed
 * from the trigger's own bounding box, escapes every ancestor's clipping
 * and stacking context.
 */
export function Tooltip({ trigger, children }: { trigger: ReactNode; children: ReactNode }) {
  const triggerRef = useRef<HTMLSpanElement>(null)
  const bubbleRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<Position | null>(null)

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return

    const anchor = triggerRef.current.getBoundingClientRect()
    const bubbleWidth = bubbleRef.current?.offsetWidth ?? 288
    const bubbleHeight = bubbleRef.current?.offsetHeight ?? 96
    const margin = 8

    const spaceAbove = anchor.top
    const placement: Position['placement'] = spaceAbove > bubbleHeight + margin ? 'top' : 'bottom'

    let left = anchor.left + anchor.width / 2 - bubbleWidth / 2
    left = Math.max(margin, Math.min(left, window.innerWidth - bubbleWidth - margin))

    const top =
      placement === 'top'
        ? anchor.top - bubbleHeight - margin
        : anchor.bottom + margin

    setPos({ top, left, placement })
  }, [open])

  return (
    <>
      <span
        ref={triggerRef}
        className="inline-flex"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        {trigger}
      </span>
      {open
        ? createPortal(
            <div
              ref={bubbleRef}
              role="tooltip"
              className="pointer-events-none fixed z-[100] w-72 rounded-xl border border-white/10 bg-slate-900/95 p-3 text-left text-xs font-normal normal-case tracking-normal text-slate-200 shadow-2xl backdrop-blur-md transition-opacity duration-100"
              style={{
                top: pos?.top ?? -9999,
                left: pos?.left ?? -9999,
                opacity: pos ? 1 : 0,
              }}
            >
              {children}
            </div>,
            document.body,
          )
        : null}
    </>
  )
}
