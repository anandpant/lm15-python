"""Terminal input ownership across browser/manual login races."""

import io
import threading
import time
import urllib.request

import pytest

from lm15.login import TerminalUI
from lm15.login.engine import CallbackListener, LoginContext, race_callback_and_manual
from lm15.login.types import ManualCodePrompt, SelectOption, SelectPrompt


def test_callback_waits_for_manual_input_before_model_prompt():
    reading = threading.Event()
    enter = threading.Event()
    dismissed = threading.Event()
    model_shown = threading.Event()
    order = []

    class Output(io.StringIO):
        def write(self, text):
            result = super().write(text)
            if "press Enter" in text:
                dismissed.set()
            if "Choose model" in text:
                model_shown.set()
            return result

    def inp(label):
        if label.startswith("Paste"):
            reading.set()
            assert enter.wait(5), "manual input was never released"
            order.append("manual released")
            return ""
        order.append("model input")
        return "1"

    ui = TerminalUI(out=Output(), inp=inp)
    ctx = LoginContext(ui=ui, deadline=time.monotonic() + 10)
    listener = CallbackListener(path="/callback", expected_state="state")
    listener.start()
    results = []
    errors = []

    def login_then_choose():
        try:
            results.append(race_callback_and_manual(ctx, listener, ManualCodePrompt("code", "Paste code")))
            results.append(ui.prompt(SelectPrompt("model", "Choose model", (SelectOption("model-a", "A"),))))
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=login_then_choose, daemon=True)
    worker.start()
    try:
        assert reading.wait(3)
        with urllib.request.urlopen(listener.redirect_uri + "?code=callback-code&state=state", timeout=3) as response:
            assert response.status == 200
        assert dismissed.wait(3)
        assert not model_shown.wait(0.4), "model prompt appeared while manual input still owned the terminal"
        enter.set()
        worker.join(3)
        assert not worker.is_alive()
        assert not errors
        assert results[0][0].code == "callback-code"
        assert results[0][1] is None
        assert results[1] == "model-a"
        assert order == ["manual released", "model input"]
    finally:
        enter.set()
        worker.join(3)
        listener.stop()


def test_dismiss_before_prompt_does_not_read_input():
    reads = []
    out = io.StringIO()
    ui = TerminalUI(out=out, inp=lambda label: reads.append(label) or "answer")
    prompt = ManualCodePrompt("code", "Paste code")
    ui.dismiss(prompt)
    assert ui.prompt(prompt) == ""
    assert reads == []
    assert "press Enter" not in out.getvalue()


@pytest.mark.parametrize("failure", [None, EOFError, KeyboardInterrupt])
def test_dismiss_after_prompt_finished_does_not_ask_for_enter(failure):
    out = io.StringIO()

    def inp(label):
        if failure:
            raise failure()
        return "pasted"

    ui = TerminalUI(out=out, inp=inp)
    prompt = ManualCodePrompt("code", "Paste code")
    if failure:
        with pytest.raises(failure):
            ui.prompt(prompt)
    else:
        assert ui.prompt(prompt) == "pasted"
        # Invalid manual returns can be retried using the same prompt object.
        assert ui.prompt(prompt) == "pasted"
    ui.dismiss(prompt)
    assert "press Enter" not in out.getvalue()
