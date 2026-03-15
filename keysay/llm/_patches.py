"""Monkey-patches for transformers 5.x when torchvision is absent.

The video_processor subsystem crashes because VIDEO_PROCESSOR_MAPPING_NAMES
values are all None without PyTorch/torchvision.  These patches are harmless
no-ops when the bug isn't present.
"""

_applied = False


def apply_transformers_patches():
    """Apply once at import time — safe to call multiple times."""
    global _applied
    if _applied:
        return
    _applied = True

    try:
        import transformers.models.auto.video_processing_auto as vpa
        import transformers.processing_utils as pu

        # 1. AutoVideoProcessor.from_pretrained raises TypeError/ValueError
        #    when torchvision is missing.
        _orig_fp = vpa.AutoVideoProcessor.from_pretrained.__func__

        @classmethod
        def _safe_fp(cls, *args, **kwargs):
            try:
                return _orig_fp(cls, *args, **kwargs)
            except (TypeError, ValueError):
                return None

        vpa.AutoVideoProcessor.from_pretrained = _safe_fp

        # 2. ProcessorMixin.__init__ rejects None video_processor.
        _orig_check = pu.ProcessorMixin.check_argument_for_proper_class

        def _safe_check(self, name, arg):
            if arg is None and "video" in name.lower():
                return
            return _orig_check(self, name, arg)

        pu.ProcessorMixin.check_argument_for_proper_class = _safe_check

    except Exception:
        pass  # transformers not installed or API changed — skip silently
