import { useRef } from "react";

export function AssetIngestDropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return <section className="vb-library-dropzone" data-testid="library-dropzone" onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }} onDrop={(event) => { event.preventDefault(); onFiles(Array.from(event.dataTransfer.files)); }}><div><strong>자산 추가</strong><p>영상·음악·효과음을 끌어다 놓으세요.</p></div><input data-native-control="asset-file-input" ref={inputRef} type="file" multiple accept=".mp4,.mov,.m4v,.webm,.mp3,.wav,.m4a,.ogg,.flac" hidden onChange={(event) => { onFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = ""; }} /><button data-native-control="asset-file-add" type="button" onClick={() => inputRef.current?.click()}>파일 추가</button></section>;
}
