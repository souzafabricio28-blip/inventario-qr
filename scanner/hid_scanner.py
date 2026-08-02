import threading
import time
import sys


class ScannerHID:
    def __init__(self, timeout=5, callback=None):
        self.buffer = ""
        self.timeout = timeout
        self.callback = callback
        self._last_time = 0
        self._running = False
        self._thread = None

    def _processar_ean(self, ean):
        print(f"\n[SCANNER] EAN lido: {ean}")
        if self.callback:
            self.callback(ean)

    def _loop_leitura(self):
        print("[SCANNER] Modo HID ativado. Aponte o scanner para o código de barras.")
        print("[SCANNER] Pressione Ctrl+C para sair do modo de leitura.\n")
        while self._running:
            try:
                char = sys.stdin.read(1)
                if not char:
                    continue

                now = time.time()

                if now - self._last_time > 0.5 and self.buffer:
                    self._processar_ean(self.buffer.strip())
                    self.buffer = ""

                self._last_time = now

                if char == "\r" or char == "\n":
                    if self.buffer:
                        ean = self.buffer.strip()
                        if ean:
                            self._processar_ean(ean)
                        self.buffer = ""
                else:
                    self.buffer += char

            except (EOFError, KeyboardInterrupt):
                break
            except Exception as e:
                print(f"[SCANNER] Erro: {e}")
                break

        if self.buffer and self.buffer.strip():
            self._processar_ean(self.buffer.strip())
            self.buffer = ""

    def iniciar(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop_leitura, daemon=True)
        self._thread.start()

    def parar(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
