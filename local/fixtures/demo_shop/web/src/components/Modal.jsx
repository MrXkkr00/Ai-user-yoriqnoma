export default function Modal({ title, children, onClose }) {
  return (
    <div className="modal-backdrop">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <h2 id="modal-title">{title}</h2>
        {children}
        <button type="button" className="secondary" onClick={onClose}>
          Yopish
        </button>
      </div>
    </div>
  );
}
