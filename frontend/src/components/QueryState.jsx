// Renders the loading / error / empty states shared by the list tabs; renders children when there is data.
export default function QueryState({ query, isEmpty, loadingText, emptyText, errorText, children }) {
  if (query.isPending) return <div className="state-message state-message--center">{loadingText}</div>
  if (query.isError) {
    return (
      <p className="state-message state-message--error" role="alert">
        {errorText}
      </p>
    )
  }
  if (isEmpty) return <p className="state-message">{emptyText}</p>
  return children
}
