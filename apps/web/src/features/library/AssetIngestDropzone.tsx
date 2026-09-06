import { useRef } from "react";

export function AssetIngestDropzone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
    // 렌더러가 그릴 수 있는 사진은 전부 받는다 -- 안 받으면 owner는 그 파일을
  // **넣을 수조차 없다**. 네 목록이 어긋나는 것은
  // `tests/test_photo_suffixes_are_one_list.py`가 잡는다.
  const accept = ".mp4,.mov,.m4v,.webm,.mp3,.wav,.m4a,.ogg,.flac,.png,.jpg,.jpeg,.webp,.bmp";
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onFiles(Array.from(event.target.files ?? []));
    event.currentTarget.value = "";
  };
  return <section className="vb-library-dropzone" data-testid="library-dropzone" onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }} onDrop={(event) => { event.preventDefault(); onFiles(Array.from(event.dataTransfer.files)); }}><div><strong>미디어 추가</strong><p>영상·음악·효과음·그림을 파일이나 폴더째 끌어다 놓으세요.</p></div><div className="vb-library-dropzone__actions"><input data-native-control="asset-file-input" ref={inputRef} type="file" multiple accept={accept} hidden onChange={handleChange} /><input data-testid="library-folder-input" data-native-control="asset-folder-input" ref={(node) => { folderInputRef.current = node; node?.setAttribute("webkitdirectory", ""); node?.setAttribute("directory", ""); }} type="file" multiple accept={accept} hidden onChange={handleChange} /><button data-native-control="asset-file-add" type="button" onClick={() => inputRef.current?.click()}>파일 추가</button><button data-native-control="asset-folder-add" type="button" onClick={() => folderInputRef.current?.click()}>폴더 추가</button></div></section>;
}
