# Let's see how long the region names list is for Indonesia ADM2
import json
import urllib.request

# Since I can't easily fetch it, I'll just simulate 519 names.
names = [f"Kabupaten {i}" for i in range(519)]
result_text = f"【IDN ADM2 行政区列表】共 519 个:\n" + ", ".join(names)
print(len(result_text))
