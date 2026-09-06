// src/App.tsx
import React, { useState } from 'react';

interface VideoFormat {
  format_id: string;
  ext: string;
  resolution: string;
  filesize: number | null;
  note: string;
  has_video: boolean;
  has_audio: boolean;
  quality: string;
}

interface VideoInfo {
  title: string;
  thumbnail?: string;
  duration: number;
  formats: VideoFormat[];
}

// Quality presets
const QUALITY_PRESETS = {
  'audio': 'Audio Only (MP3)',
  '360p': '360p',
  '720p': '720p',
  '1080p': '1080p',
  'best': 'Best Quality',
} as const;

function App() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const [selectedFormat, setSelectedFormat] = useState<string>('');
  const [selectedQuality, setSelectedQuality] = useState<keyof typeof QUALITY_PRESETS>('best');

  // Format duration in minutes and seconds
  const formatDuration = (seconds: number): string => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  // Filter formats based on quality preset
  const filterFormats = (formats: VideoFormat[]): VideoFormat[] => {
    if (selectedQuality === 'audio') {
      return formats.filter(f => !f.has_video && f.has_audio);
    }

    const heightMap = {
      '360p': 360,
      '720p': 720,
      '1080p': 1080,
    };

    const targetHeight = heightMap[selectedQuality as keyof typeof heightMap];
    if (targetHeight) {
      return formats.filter(f => {
        const height = parseInt(f.resolution.split('x')[1] || '0');
        return height <= targetHeight && height >= (targetHeight - 100);
      });
    }

    return formats;
  };

  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');
    setError('');
    setVideoInfo(null);

    try {
      const response = await fetch('http://localhost:8000/formats', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url })
      });

      if (!response.ok) {
        throw new Error('Failed to get video information');
      }

      const data = await response.json();
      setVideoInfo(data);
      
      // Set default format based on quality preset
      const filteredFormats = filterFormats(data.formats);
      if (filteredFormats.length > 0) {
        setSelectedFormat(filteredFormats[0].format_id);
      }
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    setLoading(true);
    setMessage('Starting download...');
    
    try {
      const response = await fetch('http://localhost:8000/download', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          url,
          format_id: selectedFormat 
        })
      });

      if (!response.ok) {
        throw new Error('Download failed');
      }

      const contentDisposition = response.headers.get('Content-Disposition');
      const filenameMatch = contentDisposition && contentDisposition.match(/filename="(.+)"/);
      const filename = filenameMatch ? filenameMatch[1] : 'video.mp4';

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(downloadUrl);
      document.body.removeChild(a);
      
      setMessage(`Download complete: ${filename}`);
    } catch (err: any) {
      setError(err.message || 'Download failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-2xl">
        <h1 className="text-3xl font-bold mb-6 text-center">YouTube Downloader</h1>
        
        <form onSubmit={handleUrlSubmit} className="space-y-4">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Enter YouTube URL..."
            className="w-full p-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
          
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-500 text-white p-2 rounded-md hover:bg-blue-600 disabled:bg-blue-300 disabled:cursor-not-allowed"
          >
            {loading ? 'Processing...' : 'Check Video'}
          </button>
        </form>

        {videoInfo && (
          <div className="mt-6 space-y-4">
            <div className="flex items-start space-x-4">
              {videoInfo.thumbnail && (
                <img 
                  src={videoInfo.thumbnail} 
                  alt={videoInfo.title}
                  className="w-48 h-auto rounded-md"
                />
              )}
              <div>
                <h2 className="text-xl font-semibold">{videoInfo.title}</h2>
                {videoInfo.duration && (
                  <p className="text-gray-600">
                    Duration: {formatDuration(videoInfo.duration)}
                  </p>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">
                Quality Preset
              </label>
              <select
                value={selectedQuality}
                onChange={(e) => setSelectedQuality(e.target.value as keyof typeof QUALITY_PRESETS)}
                className="w-full p-2 border border-gray-300 rounded-md"
              >
                {Object.entries(QUALITY_PRESETS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700">
                Available Formats
              </label>
              <select
                value={selectedFormat}
                onChange={(e) => setSelectedFormat(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-md"
              >
                {filterFormats(videoInfo.formats).map((format) => (
                  <option key={format.format_id} value={format.format_id}>
                    {format.resolution === 'N/A' ? 'Audio Only' : format.resolution} - {format.note}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleDownload}
              disabled={loading}
              className="w-full bg-green-500 text-white p-2 rounded-md hover:bg-green-600 disabled:bg-green-300 disabled:cursor-not-allowed"
            >
              {loading ? 'Downloading...' : 'Download'}
            </button>
          </div>
        )}

        {message && (
          <div className="mt-4 p-3 bg-green-100 text-green-700 rounded-md">
            {message}
          </div>
        )}

        {error && (
          <div className="mt-4 p-3 bg-red-100 text-red-700 rounded-md">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;