import time, numpy as np, onnxruntime as ort
s = ort.InferenceSession("app/weights/best.onnx", providers=["CPUExecutionProvider"])
n = s.get_inputs()[0].name
x = np.random.rand(1, 3, 640, 640).astype(np.float32)
for _ in range(5): s.run(None, {n: x})   # pemanasan
t = time.perf_counter()
for _ in range(50): s.run(None, {n: x})
dt = (time.perf_counter() - t) / 50
print(f"{dt*1000:.0f} ms/frame = {1/dt:.1f} FPS (inferensi saja)")