import type { CharacterStatesResponse } from "../api/types";
import { changeLabels, dimensionLabels, label } from "../lib/labels";

interface Props {
  states: CharacterStatesResponse;
  position: number;
  onPositionChange: (position: number) => void;
}

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 74;
const TRACK_Y = 26;
const TRACK_HEIGHT = 22;

const DIMENSION_COLORS: Record<string, string> = {
  life: "#8e44ad",
  form: "#2980b9",
  scene: "#16a085",
  appearance: "#d35400",
};

export default function SegmentTimeline({ states, position, onPositionChange }: Props) {
  const total = states.processed_source_end || 1;
  const toX = (cp: number) => (cp / total) * VIEW_WIDTH;

  const handleClick = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const cp = Math.max(0, Math.min(total - 1, Math.round(ratio * total)));
    onPositionChange(cp);
  };

  return (
    <div className="timeline">
      <div className="pane-header">
        <h2>状态区间时间线</h2>
        <span className="muted small">
          点击时间线设置阅读位置 · 当前位置 {position} / {total}
        </span>
      </div>
      <svg
        className="timeline-svg"
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        preserveAspectRatio="none"
        onClick={handleClick}
      >
        <rect x={0} y={TRACK_Y} width={VIEW_WIDTH} height={TRACK_HEIGHT} className="timeline-track" />
        {states.state_segments.map((segment) => (
          <g key={segment.state_segment_id}>
            <rect
              x={toX(segment.document_span.start)}
              y={TRACK_Y}
              width={Math.max(1, toX(segment.document_span.end) - toX(segment.document_span.start))}
              height={TRACK_HEIGHT}
              className={
                "timeline-segment" +
                (segment.start_boundary.position <= position && position < segment.end_boundary.position
                  ? " timeline-segment-current"
                  : "")
              }
            >
              <title>
                {`区间 ${segment.sequence_index}: [${segment.document_span.start}, ${segment.document_span.end})\n` +
                  `life=${segment.life} / form=${segment.form} / scene=${segment.scene}`}
              </title>
            </rect>
            <text
              x={toX(segment.document_span.start) + 3}
              y={TRACK_Y + TRACK_HEIGHT - 6}
              className="timeline-segment-index"
            >
              {segment.sequence_index}
            </text>
          </g>
        ))}
        {states.transitions.map((transition) => (
          <g key={transition.transition_id}>
            <line
              x1={toX(transition.document_span.start)}
              x2={toX(transition.document_span.start)}
              y1={TRACK_Y - 10}
              y2={TRACK_Y + TRACK_HEIGHT + 10}
              stroke={DIMENSION_COLORS[transition.dimension] ?? "#7f8c8d"}
              strokeWidth={1.5}
            >
              <title>
                {`${label(dimensionLabels, transition.dimension)} · ${label(changeLabels, transition.change)} · ${transition.attribute}\n` +
                  `${transition.evidence}`}
              </title>
            </line>
            <circle
              cx={toX(transition.document_span.start)}
              cy={TRACK_Y - 12}
              r={3.5}
              fill={DIMENSION_COLORS[transition.dimension] ?? "#7f8c8d"}
            >
              <title>{`${transition.attribute}: ${transition.before || "∅"} → ${transition.after || "∅"}`}</title>
            </circle>
          </g>
        ))}
        <line
          x1={toX(position)}
          x2={toX(position)}
          y1={4}
          y2={VIEW_HEIGHT - 4}
          className="timeline-position"
        />
      </svg>
      <div className="timeline-slider">
        <input
          type="range"
          min={0}
          max={Math.max(0, total - 1)}
          value={Math.min(position, total - 1)}
          onChange={(event) => onPositionChange(Number(event.target.value))}
        />
      </div>
      <div className="timeline-legend muted small">
        {Object.entries(DIMENSION_COLORS).map(([dimension, color]) => (
          <span key={dimension}>
            <span className="legend-dot" style={{ background: color }} />
            {label(dimensionLabels, dimension)}
          </span>
        ))}
      </div>
    </div>
  );
}
