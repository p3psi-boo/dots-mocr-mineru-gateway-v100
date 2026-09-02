import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = workerUrl;

export { getDocument };
export type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';

export async function countPdfPages(file: File): Promise<number | null> {
  if (file.type !== 'application/pdf' && !/\.pdf$/i.test(file.name)) return null;
  try {
    const buffer = await file.arrayBuffer();
    const loading = getDocument({ data: new Uint8Array(buffer) });
    const pdf = await loading.promise;
    const pages = pdf.numPages;
    await pdf.destroy();
    return pages;
  } catch {
    return null;
  }
}
