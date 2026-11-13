import { useCallback, useRef, useState } from 'react';
import type { Offer } from '../types';
import { describeError, submitOffer } from '../api';
import { allowedMimeTypes, maxFileBytes, maxFileSizeLabel } from '../config';
import { formatBytes } from '../lib/format';

interface UploadScreenProps {
  onSubmitted: (offer: Offer, previewUrl: string | null) => void;
}

interface FormState {
  file: File | null;
  caption: string;
  location: string;
  shotAt: string;
}

function validateFile(file: File): string | null {
  if (!allowedMimeTypes.includes(file.type)) {
    return 'Такой формат не поддерживается. Нужен JPEG, PNG или WebP.';
  }
  if (file.size > maxFileBytes) {
    return `Файл весит ${formatBytes(file.size)} — больше лимита ${maxFileSizeLabel}.`;
  }
  return null;
}

/** Экран загрузки: файл, подпись, место, время съёмки → POST /api/offers. */
export function UploadScreen({ onSubmitted }: UploadScreenProps) {
  const [form, setForm] = useState<FormState>({ file: null, caption: '', location: '', shotAt: '' });
  const [preview, setPreview] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [sending, setSending] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const acceptFile = useCallback((file: File) => {
    const error = validateFile(file);
    setFileError(error);
    if (error) {
      setForm((prev) => ({ ...prev, file: null }));
      setPreview((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return;
    }
    setForm((prev) => ({ ...prev, file }));
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
  }, []);

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) acceptFile(file);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.file) {
      setFileError('Выберите файл — без него заявку не создать.');
      return;
    }
    setFormError(null);
    setSending(true);
    try {
      const offer = await submitOffer({
        file: form.file,
        caption: form.caption.trim(),
        location: form.location.trim(),
        shotAt: form.shotAt ? new Date(form.shotAt).toISOString() : '',
      });
      onSubmitted(offer, preview);
    } catch (error) {
      setFormError(describeError(error));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="screen screen--upload">
      <div className="screen__head">
        <p className="eyebrow">заявка на лот</p>
        <h1 className="screen__title">Загрузите кадр с места</h1>
        <p className="screen__lead">
          Система проверит подлинность и оригинальность файла, оценит материал и предложит цену.
          Публиковать до проверки ничего не нужно.
        </p>
      </div>

      {formError && (
        <div className="alert" role="alert">
          <div>
            <p className="alert__title">Не удалось отправить файл</p>
            <p className="alert__text">{formError}</p>
          </div>
        </div>
      )}

      <form className="card upload" onSubmit={(event) => void handleSubmit(event)}>
        <div
          className={`dropzone${dragging ? ' is-dragging' : ''}${preview ? ' has-file' : ''}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          {preview ? (
            <img className="dropzone__preview" src={preview} alt="Превью выбранного файла" />
          ) : (
            <div className="dropzone__empty">
              <p className="dropzone__title">Перетащите файл сюда</p>
              <p className="dropzone__hint">JPEG, PNG или WebP · до {maxFileSizeLabel}</p>
            </div>
          )}
          <input
            ref={inputRef}
            id="offer-file"
            className="visually-hidden"
            type="file"
            accept={allowedMimeTypes.join(',')}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) acceptFile(file);
            }}
          />
          <button
            type="button"
            className="btn btn--ghost btn--sm dropzone__pick"
            onClick={() => inputRef.current?.click()}
            disabled={sending}
          >
            {preview ? 'Другой файл' : 'Выбрать файл'}
          </button>
        </div>

        {fileError && (
          <p className="field__error" role="alert">
            {fileError}
          </p>
        )}

        {form.file && !fileError && (
          <p className="upload__filemeta">
            {form.file.name} · {formatBytes(form.file.size)}
          </p>
        )}

        <div className="field">
          <label className="field__label" htmlFor="caption">
            Подпись
          </label>
          <input
            id="caption"
            className="field__input"
            type="text"
            maxLength={200}
            value={form.caption}
            placeholder="Что происходит на кадре"
            onChange={(event) => setForm((prev) => ({ ...prev, caption: event.target.value }))}
            disabled={sending}
          />
        </div>

        <div className="field-grid">
          <div className="field">
            <label className="field__label" htmlFor="location">
              Место
            </label>
            <input
              id="location"
              className="field__input"
              type="text"
              maxLength={120}
              value={form.location}
              placeholder="Город, улица"
              onChange={(event) => setForm((prev) => ({ ...prev, location: event.target.value }))}
              disabled={sending}
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="shot_at">
              Когда снято
            </label>
            <input
              id="shot_at"
              className="field__input"
              type="datetime-local"
              value={form.shotAt}
              max={new Date().toISOString().slice(0, 16)}
              onChange={(event) => setForm((prev) => ({ ...prev, shotAt: event.target.value }))}
              disabled={sending}
            />
          </div>
        </div>

        <div className="actions">
          <button type="submit" className="btn btn--primary" disabled={sending || !form.file}>
            {sending ? 'Отправляем…' : 'Отправить на проверку'}
          </button>
        </div>

        {sending && (
          <p className="loading" role="status">
            <span className="spinner" aria-hidden="true" />
            Загружаем файл и запускаем проверку
          </p>
        )}
      </form>
    </div>
  );
}