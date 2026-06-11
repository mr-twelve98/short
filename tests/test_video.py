import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.video_processor import format_timestamp, process_clip

class TestVideoProcessor(unittest.TestCase):
    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(0), "00:00:00,000")
        self.assertEqual(format_timestamp(3661.123), "01:01:01,123")

    @patch('src.video_processor.ensure_tools')
    @patch('src.video_processor.download_video')
    @patch('src.video_processor.cut_clip')
    @patch('src.video_processor.transcribe_clip')
    @patch('src.smart_crop.get_smart_crop_params')
    def test_process_clip(self, mock_crop, mock_transcribe, mock_cut, mock_download, mock_tools):
        mock_download.return_value = Path("downloads/video.mp4")
        mock_crop.return_value = 0
        # Simulate file exists check
        with patch.object(Path, 'exists', return_value=True):
            clip_dict = {'clip': 1, 'start': '00:00:10', 'end': '00:00:40'}
            mock_transcribe.return_value = Path("temp/clip_1.srt")

            clip_path, srt_path, crop_x = process_clip(clip_dict, "http://url", "none", "tiny")

            mock_tools.assert_called_once()
            mock_download.assert_called_with("http://url")
            mock_cut.assert_called()
            mock_transcribe.assert_called()

            self.assertEqual(clip_path, Path("temp/clip_1.mp4"))
            self.assertEqual(srt_path, Path("temp/clip_1.srt"))
            self.assertEqual(crop_x, 0)

if __name__ == '__main__':
    unittest.main()
