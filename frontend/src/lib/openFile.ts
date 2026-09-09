import { useMutation } from '@tanstack/react-query';
import { openFile } from '../api';

/** Opens a finished download in whatever the OS plays it with. */
export function useOpenFile(onError?: () => void) {
  return useMutation({ mutationFn: openFile, onError });
}
