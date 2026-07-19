export function Skeleton({ className = "", lines = 1 }) {
  if (lines <= 1) {
    return <div className={`skeleton ${className}`} aria-hidden="true" />;
  }
  return (
    <div className={`skeleton-group ${className}`} aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <div key={index} className="skeleton" />
      ))}
    </div>
  );
}

export function SkeletonMeters({ count = 6 }) {
  return (
    <div className="meters">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="meter">
          <div className="meter-head">
            <Skeleton className="skeleton-sm" />
            <Skeleton className="skeleton-xs" />
          </div>
          <Skeleton className="skeleton-bar" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonBoard({ count = 6 }) {
  return (
    <ul className="board-list" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <li key={index} className="board-row">
          <span className="skeleton skeleton-rank" />
          <div className="board-main">
            <div className="board-name-line">
              <Skeleton className="skeleton-sm" />
              <Skeleton className="skeleton-xs" />
            </div>
            <Skeleton className="skeleton-bar" />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {Array.from({ length: cols }, (_, index) => (
              <th key={index}>
                <Skeleton className="skeleton-sm" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, rowIndex) => (
            <tr key={rowIndex}>
              {Array.from({ length: cols }, (_, colIndex) => (
                <td key={colIndex}>
                  <Skeleton />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
