from pathlib import Path
from stytra import Stytra
from PyQt5.QtWidgets import (
    QFileDialog,
    QApplication,
    QDialog,
    QPushButton,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QLabel,
    QToolBar,
    QProgressBar,
    QVBoxLayout,
)
import qdarkstyle
from stytra.stimulation import Protocol
from stytra.stimulation.stimuli import Stimulus
from stytra.experiments.fish_pipelines import pipeline_dict
from stytra.utilities import save_df
import imageio
import pandas as pd
import json
from types import MethodType
from stytra.experiments import VisualExperiment
from stytra.tracking.preprocessing import BackgroundSubtractor


OFFLINE_PROCESS_JOIN_TIMEOUT = 2.0


def clear_queue(queue):
    if queue is None:
        return
    try:
        queue.clear()
    except AttributeError:
        pass


def join_or_terminate(process, timeout=OFFLINE_PROCESS_JOIN_TIMEOUT):
    if process is None:
        return
    try:
        process.join(timeout)
    except AssertionError:
        return
    if process.is_alive():
        process.terminate()
        process.join(timeout)


def wrap_up_offline_experiment(exp):
    exp.gui_timer.stop()
    VisualExperiment.wrap_up(exp)

    exp.camera.kill_event.set()
    clear_queue(getattr(exp.camera, "frame_queue", None))

    frame_dispatcher = getattr(exp, "frame_dispatcher", None)
    clear_queue(getattr(frame_dispatcher, "gui_queue", None))
    clear_queue(getattr(frame_dispatcher, "frame_copy_queue", None))

    join_or_terminate(frame_dispatcher)
    join_or_terminate(exp.camera)


def install_offline_close_handler(window, app):
    def close_event(self, event):
        wrap_up_offline_experiment(self.experiment)
        event.accept()
        app.quit()

    window.closeEvent = MethodType(close_event, window)


def get_video_reader(input_path):
    try:
        return imageio.get_reader(str(input_path), "ffmpeg")
    except ImportError as exc:
        raise ImportError(
            "Could not open video with imageio's FFMPEG plugin. "
            "Install the missing conda dependency with:\n"
            "C:\\Users\\huang\\AppData\\Local\\anaconda3\\condabin\\conda.bat "
            "run -n stytra python -m pip install \"imageio[ffmpeg]\""
        ) from exc


def get_reader_length(reader):
    length_methods = ("count_frames", "get_length")
    for method_name in length_methods:
        method = getattr(reader, method_name, None)
        if method is None:
            continue
        try:
            length = method()
        except Exception:
            continue
        if length is not None and length > 0 and length != float("inf"):
            return int(length)
    return None


def valid_positive_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value > 0 and value != float("inf"):
        return value
    return None


def fps_from_frame_count(n_frames, duration):
    duration = valid_positive_float(duration)
    if n_frames is None or duration is None:
        return None
    return n_frames / duration


def count_frames_and_secs(input_path):
    try:
        import imageio_ffmpeg
    except ImportError:
        return None, None

    try:
        return imageio_ffmpeg.count_frames_and_secs(str(input_path))
    except Exception:
        return None, None


def select_fps(metadata_fps, counted_fps):
    metadata_fps = valid_positive_float(metadata_fps)
    counted_fps = valid_positive_float(counted_fps)
    if metadata_fps is None:
        return counted_fps or 30
    if counted_fps is None:
        return metadata_fps
    if abs(metadata_fps - counted_fps) / metadata_fps > 0.001:
        return counted_fps
    return metadata_fps


def get_video_metadata(reader, input_path, n_frames=None):
    metadata = {}
    get_meta_data = getattr(reader, "get_meta_data", None)
    if get_meta_data is not None:
        try:
            metadata.update(get_meta_data())
        except Exception:
            pass

    counted_fps = fps_from_frame_count(n_frames, metadata.get("duration"))
    if counted_fps is None:
        counted_frames, counted_secs = count_frames_and_secs(input_path)
        counted_fps = fps_from_frame_count(counted_frames, counted_secs)

    metadata["fps"] = select_fps(metadata.get("fps"), counted_fps)
    return metadata


def get_background_difference_node(pipeline):
    for node in pipeline.node_dict.values():
        if isinstance(node, BackgroundSubtractor):
            return node
    return None


def background_difference_output_path(input_path):
    return input_path.with_name(
        input_path.stem + "_background_difference" + input_path.suffix
    )


def ffmpeg_bitrate_arg(bitrate):
    if bitrate is None:
        return None
    if isinstance(bitrate, str):
        return bitrate
    if bitrate <= 0:
        return None
    return "{}k".format(max(1, int(round(bitrate / 1000))))


class EmptyProtocol(Protocol):
    name = "Offline"

    def get_stim_sequence(self):
        return [Stimulus(duration=5.0)]


class TrackingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QVBoxLayout())
        self.setWindowTitle("Tracking")
        self.prog_track = QProgressBar()
        self.lbl_status = QLabel()
        self.layout().addWidget(self.prog_track)
        self.layout().addWidget(self.lbl_status)


class OfflineToolbar(QToolBar):
    def __init__(self, app, exp, input_path, pipeline_type):
        super().__init__()
        self.app = app
        self.setObjectName("toolbar_offline")
        self.exp = exp
        self.input_path = Path(input_path)
        self.pipeline_type = pipeline_type
        self.output_path = self.input_path.parent / self.input_path.stem

        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItems(["csv", "feather", "hdf5"])
        self.chk_save_bgdiff = QCheckBox("Save background difference video")
        self.chk_save_bgdiff.setEnabled(
            get_background_difference_node(self.exp.pipeline) is not None
        )

        self.addAction("Track video", self.track)
        self.addWidget(self.chk_save_bgdiff)
        self.addAction("Output format")
        self.addWidget(self.cmb_fmt)
        self.addSeparator()
        self.addAction("Save tracking params", self.save_params)

        self.diag_track = TrackingDialog(self.exp.window_main)

    def track(self):
        fileformat = self.cmb_fmt.currentText()

        self.exp.camera.kill_event.set()
        sync_background = getattr(self.exp, "sync_tracking_background_from_process", None)
        if sync_background is not None and sync_background():
            self.diag_track.lbl_status.setText("Using current preview background")
        reader = get_video_reader(self.input_path)
        bgdiff_node = get_background_difference_node(self.exp.pipeline)
        save_bgdiff_video = self.chk_save_bgdiff.isChecked() and bgdiff_node is not None
        bgdiff_writer = None
        bgdiff_output_name = str(background_difference_output_path(self.input_path))
        data = []
        try:
            self.exp.window_main.stream_plot.toggle_freeze()

            output_name = str(self.output_path) + "." + fileformat
            self.diag_track.show()
            n_frames = get_reader_length(reader)
            if n_frames is None:
                self.diag_track.prog_track.setRange(0, 0)
            else:
                self.diag_track.prog_track.setRange(0, n_frames)
            video_metadata = get_video_metadata(reader, self.input_path, n_frames)
            self.diag_track.lbl_status.setText("Tracking to " + output_name)
            if save_bgdiff_video:
                self.diag_track.lbl_status.setText(
                    "Tracking to {} and {}".format(output_name, bgdiff_output_name)
                )

            for i, frame in enumerate(reader):
                data.append(self.exp.pipeline.run(frame[:, :, 0]).data)
                if save_bgdiff_video:
                    if bgdiff_writer is None:
                        writer_kwargs = dict(
                            fps=video_metadata["fps"],
                            quality=None,
                            macro_block_size=None,
                            ffmpeg_params=["-pix_fmt", "yuv420p"],
                        )
                        bitrate = ffmpeg_bitrate_arg(video_metadata.get("bitrate"))
                        if bitrate is not None:
                            writer_kwargs["bitrate"] = bitrate
                        bgdiff_writer = imageio.get_writer(
                            bgdiff_output_name, "ffmpeg", **writer_kwargs
                        )
                    bgdiff_writer.append_data(bgdiff_node.last_output_image)
                if n_frames is not None:
                    self.diag_track.prog_track.setValue(i + 1)
                if i % 100 == 0:
                    if n_frames is None:
                        self.diag_track.lbl_status.setText(
                            "Tracking frame {} to {}".format(i + 1, output_name)
                        )
                    self.app.processEvents()

            if bgdiff_writer is not None:
                self.diag_track.lbl_status.setText("Finalizing " + bgdiff_output_name)
                self.app.processEvents()
                bgdiff_writer.close()
                bgdiff_writer = None

            self.diag_track.lbl_status.setText("Saving " + output_name)
            self.diag_track.prog_track.setRange(0, 1)
            self.diag_track.prog_track.setValue(0)
            df = pd.DataFrame.from_records(data, columns=data[0]._fields)
            save_df(df, self.output_path, fileformat)
            self.diag_track.prog_track.setValue(1)
            completed_message = "Completed " + output_name
            if save_bgdiff_video:
                completed_message += " and " + bgdiff_output_name
            self.diag_track.lbl_status.setText(completed_message)
        finally:
            if bgdiff_writer is not None:
                bgdiff_writer.close()
            close = getattr(reader, "close", None)
            if close is not None:
                close()

    def save_params(self):
        params = self.exp.pipeline.serialize_params()
        json.dump(
            dict(pipeline_type=self.pipeline_type, pipeline_params=params),
            open(str(self.output_path) + "_trackingparams.json", "w"),
        )


class StytraLoader(QDialog):
    """A quick-and-dirty monkey-patch of Stytra for easy offline tracking"""

    def __init__(self, app):
        super().__init__()
        self.setWindowTitle("Select video for offline tracking")
        self.app = app

        self.btn_vid = QPushButton("Select video")
        self.btn_vid.clicked.connect(self.select_video)
        self.filename = None
        self.lbl_filename = QLabel("")

        self.lbl_whattrack = QLabel("What to track")
        self.cmb_tracking = QComboBox()
        self.cmb_tracking.addItems(list(pipeline_dict.keys()))

        self.btn_start = QPushButton("Start stytra")
        self.btn_start.clicked.connect(self.run_stytra)
        self.btn_start.setEnabled(False)

        self.setLayout(QGridLayout())
        self.layout().addWidget(self.btn_vid, 0, 0)
        self.layout().addWidget(self.lbl_filename, 0, 1)

        self.layout().addWidget(self.lbl_whattrack, 1, 0)
        self.layout().addWidget(self.cmb_tracking, 1, 1)

        self.layout().addWidget(self.btn_start, 2, 0, 1, 2)

        self.stytra = None

    def select_video(self):
        fn, _ = QFileDialog.getOpenFileName(
            None, "Select video file", filter="Videos (*.avi *.mov *.mp4)"
        )
        self.filename = fn
        self.lbl_filename.setText(self.filename)
        self.btn_start.setEnabled(True)

    def run_stytra(self):
        self.stytra = Stytra(
            app=self.app,
            protocol=EmptyProtocol(),
            camera=dict(video_file=self.filename),
            tracking=dict(method=self.cmb_tracking.currentText()),
            exec=False,
            offline=True,
            display=dict(gl_display=False),
        )

        offline_toolbar = OfflineToolbar(
            self.app,
            self.stytra.exp,
            self.filename,
            pipeline_type=self.cmb_tracking.currentText(),
        )

        self.stytra.exp.window_main.toolbar_control.hide()
        self.stytra.exp.window_main.addToolBar(offline_toolbar)
        offline_toolbar.show()
        install_offline_close_handler(self.stytra.exp.window_main, self.app)

        self.close()


if __name__ == "__main__":
    app = QApplication([])
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    ld = StytraLoader(app)
    ld.show()
    app.exec()
