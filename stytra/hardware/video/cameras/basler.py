from stytra.hardware.video.cameras.interface import Camera, CameraError

try:
    from pypylon import pylon
except ImportError:
    pylon = None


class BaslerCamera(Camera):
    """Basler camera control through pypylon.

    ROI is (x, y, width, height). Use -1 for full width/height and minimum
    offset. This implementation is intentionally simple and assumes a
    single-camera setup.
    """

    # Change these two values to switch binning policy, e.g.
    # BINNING_SELECTOR = "Sensor"; BINNING_MODE = "Average"
    BINNING_SELECTOR = "Region1"
    BINNING_MODE = "Sum"

    def __init__(self, cam_idx=0, **kwargs):
        super().__init__(**kwargs)

        if pylon is None:
            raise CameraError("The pypylon package must be installed to use a Basler camera.")
        if cam_idx != 0:
            raise CameraError("BaslerCamera only supports the first camera in this setup.")

        devices = pylon.TlFactory.GetInstance().EnumerateDevices()
        if len(devices) == 0:
            raise CameraError("No Basler camera found.")

        self.camera = pylon.InstantCamera(pylon.FirstFound)
        self.cam = self.camera

        self.acquisition_rate_node = None
        self.exposure_time_node = None
        self.gain_node = None

    def _node(self, name):
        try:
            node = getattr(self.camera, name)
        except Exception:
            return None

        try:
            if hasattr(node, "IsValid") and not node.IsValid():
                return None
        except Exception:
            return None

        return node

    def _first_node(self, names):
        for name in names:
            node = self._node(name)
            if node is not None:
                return node
        return None

    def _try_set(self, name, value, correction=None):
        node = self._node(name)
        if node is None:
            return False

        try:
            if hasattr(node, "TrySetValue"):
                if correction is None:
                    return node.TrySetValue(value)
                return node.TrySetValue(value, correction)
            if hasattr(node, "SetValue"):
                if correction is None:
                    node.SetValue(value)
                else:
                    node.SetValue(value, correction)
            else:
                node.Value = value
            return True
        except Exception:
            return False

    def _set_min(self, name):
        node = self._node(name)
        if node is None:
            return False

        try:
            if hasattr(node, "TrySetToMinimum") and node.TrySetToMinimum():
                return True
            return self._try_set(name, node.Min, pylon.IntegerValueCorrection_Nearest)
        except Exception:
            return False

    def _set_max(self, name):
        node = self._node(name)
        if node is None:
            return False

        try:
            if hasattr(node, "TrySetToMaximum") and node.TrySetToMaximum():
                return True
            return self._try_set(name, node.Max, pylon.IntegerValueCorrection_Nearest)
        except Exception:
            return False

    def _value(self, name, default=None):
        node = self._node(name)
        if node is None:
            return default

        try:
            if hasattr(node, "GetValue"):
                return node.GetValue()
            return node.Value
        except Exception:
            return default

    def _set_binning(self, messages):
        try:
            downsampling = int(self.downsampling)
        except Exception:
            downsampling = 1

        if downsampling not in (1, 2, 3, 4):
            messages.append(
                "W: Basler downsampling only supports 1, 2, 3, or 4. "
                "Using downsampling=1."
            )
            downsampling = 1

        if not self._try_set("BinningSelector", self.BINNING_SELECTOR):
            messages.append(
                "W: Could not set Basler BinningSelector to {0}.".format(
                    self.BINNING_SELECTOR
                )
            )

        if not self._try_set("BinningHorizontalMode", self.BINNING_MODE):
            messages.append(
                "W: Could not set Basler BinningHorizontalMode to {0}.".format(
                    self.BINNING_MODE
                )
            )

        if not self._try_set("BinningVerticalMode", self.BINNING_MODE):
            messages.append(
                "W: Could not set Basler BinningVerticalMode to {0}.".format(
                    self.BINNING_MODE
                )
            )

        for name in ("BinningHorizontal", "BinningVertical"):
            if not self._try_set(name, downsampling, pylon.IntegerValueCorrection_Nearest):
                messages.append("W: Could not set Basler {0}.".format(name))
                continue

            actual = self._value(name, downsampling)
            if actual != downsampling:
                messages.append(
                    "W: Basler {0} set to {1} instead of {2}.".format(
                        name, actual, downsampling
                    )
                )

    def _set_roi(self, messages):
        try:
            x, y, width, height = [int(v) for v in self.roi]
        except Exception:
            messages.append("E:Basler ROI must be (x, y, width, height).")
            return

        # Offsets constrain max Width/Height, so reset them before dimensions.
        self._set_min("OffsetX")
        self._set_min("OffsetY")

        if width == -1:
            self._set_max("Width")
        elif not self._try_set("Width", width, pylon.IntegerValueCorrection_Nearest):
            messages.append("W: Could not set Basler Width.")

        if height == -1:
            self._set_max("Height")
        elif not self._try_set("Height", height, pylon.IntegerValueCorrection_Nearest):
            messages.append("W: Could not set Basler Height.")

        if x == -1:
            self._set_min("OffsetX")
        elif not self._try_set("OffsetX", x, pylon.IntegerValueCorrection_Nearest):
            messages.append("W: Could not set Basler OffsetX.")

        if y == -1:
            self._set_min("OffsetY")
        elif not self._try_set("OffsetY", y, pylon.IntegerValueCorrection_Nearest):
            messages.append("W: Could not set Basler OffsetY.")

    def _configure_controls(self):
        self._try_set("AcquisitionMode", "Continuous")
        self._try_set("AcquisitionFrameRateAuto", "Off")
        self._try_set("AcquisitionFrameRateEnable", True)
        self._try_set("AcquisitionFrameRateEnabled", True)
        self._try_set("ExposureAuto", "Off")
        self._try_set("GainAuto", "Off")

        self.acquisition_rate_node = self._first_node(
            ("AcquisitionFrameRate", "AcquisitionFrameRateAbs")
        )
        self.exposure_time_node = self._first_node(("ExposureTime", "ExposureTimeAbs"))
        self.gain_node = self._first_node(("Gain", "GainRaw"))

    def open_camera(self):
        messages = []
        try:
            self.camera.Open()
            self._set_binning(messages)
            self._set_roi(messages)
            self._configure_controls()
            self.camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
            messages.append("I:Basler camera opened")
        except Exception as ex:
            messages.append("E:Could not open Basler camera. Exception: {0}.".format(ex))
        return messages

    def _set_float(self, node, value, messages, name):
        if node is None:
            messages.append("E:{0} node is not available.".format(name))
            return

        value = float(value)
        try:
            value = min(max(value, node.Min), node.Max)
        except Exception:
            pass

        try:
            node.SetValue(value, pylon.FloatValueCorrection_ClipToRange)
        except TypeError:
            node.SetValue(value)
        except Exception as ex:
            messages.append(
                "E:Could not set Basler {0} to {1}. Exception: {2}.".format(
                    name, value, ex
                )
            )

    def set(self, param, val):
        messages = []
        try:
            if param == "exposure":
                self._set_float(self.exposure_time_node, float(val) * 1000.0, messages, param)
            elif param == "framerate":
                self._set_float(self.acquisition_rate_node, val, messages, param)
            elif param == "gain":
                self._set_float(self.gain_node, val, messages, param)
            else:
                messages.append("W: {0} not implemented".format(param))
        except Exception as ex:
            messages.append("E: BaslerCamera.set() error: {0}".format(ex))
        return messages

    def read(self):
        grab_result = None
        try:
            grab_result = self.camera.RetrieveResult(
                5000, pylon.TimeoutHandling_ThrowException
            )
            if grab_result.GrabSucceeded():
                return grab_result.Array.copy()
            return None
        except Exception as ex:
            raise CameraError("Frame not read: {0}".format(ex))
        finally:
            if grab_result is not None:
                grab_result.Release()

    def release(self):
        try:
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
        except Exception:
            pass

        try:
            if self.camera.IsOpen():
                self.camera.Close()
        except Exception:
            pass
