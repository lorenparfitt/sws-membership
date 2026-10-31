import { useEffect, useRef, useState, type PointerEvent } from "react";

interface Props {
  label: string;
  onChange: (pngDataUrl: string | null) => void;
}

// A plain canvas drawn with pointer events: works with mouse, finger and pen.
export function SignaturePad({ label, onChange }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [empty, setEmpty] = useState(true);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const scale = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * scale;
    canvas.height = canvas.clientHeight * scale;
    const context = canvas.getContext("2d")!;
    context.scale(scale, scale);
    context.lineWidth = 2.2;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = "#111";
  }, []);

  function point(event: PointerEvent<HTMLCanvasElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  function start(event: PointerEvent<HTMLCanvasElement>) {
    drawing.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    const context = event.currentTarget.getContext("2d")!;
    const { x, y } = point(event);
    context.beginPath();
    context.moveTo(x, y);
  }

  function move(event: PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const context = event.currentTarget.getContext("2d")!;
    const { x, y } = point(event);
    context.lineTo(x, y);
    context.stroke();
    if (empty) setEmpty(false);
  }

  function end(event: PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    drawing.current = false;
    // A tap that drew nothing is not a signature.
    onChange(empty ? null : event.currentTarget.toDataURL("image/png"));
  }

  function clear() {
    const canvas = canvasRef.current!;
    const context = canvas.getContext("2d")!;
    context.clearRect(0, 0, canvas.width, canvas.height);
    setEmpty(true);
    onChange(null);
  }

  return (
    <div className="signature">
      <div className="signature-head">
        <span>{label}</span>
        <button type="button" className="link" onClick={clear} disabled={empty}>
          Clear
        </button>
      </div>
      <canvas
        ref={canvasRef}
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
        aria-label={label}
      />
      {empty && <p className="label">Draw your signature above with a finger, pen or mouse.</p>}
    </div>
  );
}
