import { useMemo } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.use({
  gfm: true,
  breaks: true,
});

/**
 * Markdown 본문 렌더 — marked 로 HTML 변환 후 DOMPurify 로 sanitize.
 * format='text' 면 plaintext 로 표시.
 */
export function MarkdownPreview({ body, format = 'markdown' }) {
  const html = useMemo(() => {
    if (!body) return '';
    if (format === 'text') {
      return DOMPurify.sanitize(body.replace(/\n/g, '<br/>'));
    }
    const raw = marked.parse(body, { async: false });
    return DOMPurify.sanitize(raw);
  }, [body, format]);

  if (!body) return <p className="muted">미리보기 없음</p>;
  return <div className="md-preview" dangerouslySetInnerHTML={{ __html: html }} />;
}
