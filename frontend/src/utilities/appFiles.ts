import { Browser } from '@capacitor/browser';
import { FileOpener } from '@capacitor-community/file-opener';
import { Directory, Filesystem } from '@capacitor/filesystem';

/** Opens files and links inside the Android app, where new browser tabs do not exist. */
export class AppFiles {
  /**
   * Saves a file in the app's cache folder and opens it in the phone's viewer for its type.
   * @param blob The file's contents.
   * @param fileName The file's name, which also tells Android its type.
   */
  async open(blob: Blob, fileName: string): Promise<void> {
    const saved = await Filesystem.writeFile({
      path: `opened/${this.safeName(fileName)}`,
      data: await this.base64(blob),
      directory: Directory.Cache,
      recursive: true,
    });
    await FileOpener.open({
      filePath: saved.uri,
      contentType: blob.type || 'application/octet-stream',
    });
  }

  /**
   * Opens a web link in an in-app browser sheet, like the Claude app does.
   * @param address The link.
   */
  async openLink(address: string): Promise<void> {
    await Browser.open({ url: address });
  }

  /**
   * Makes a file name safe to use as a path.
   * @param fileName The name.
   * @returns The name with folder separators replaced.
   */
  private safeName(fileName: string): string {
    return fileName.replace(/[\\/]/g, '_') || 'file';
  }

  /**
   * Encodes a file as base64, the form the filesystem plugin writes.
   * @param blob The file.
   * @returns The base64 text without the data: prefix.
   */
  private base64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const text = reader.result as string;
        resolve(text.slice(text.indexOf(',') + 1));
      };
      reader.onerror = () => {
        reject(reader.error ?? new Error('The file could not be read.'));
      };
      reader.readAsDataURL(blob);
    });
  }
}

export const appFiles = new AppFiles();
