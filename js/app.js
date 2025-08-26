const canvasElement = document.getElementById("output");
const canvasCtx = canvasElement.getContext("2d");
const statusElement = document.getElementById("status");

// Create hidden video element (used only for MediaPipe input)
const videoElement = document.createElement("video");
videoElement.setAttribute("playsinline", "");
videoElement.setAttribute("muted", "");
videoElement.setAttribute("autoplay", "");

function calculateHeadPose(landmarks) {
  const leftEye = landmarks[33];   // left eye
  const rightEye = landmarks[263]; // right eye
  const noseTip = landmarks[1];    // nose tip

  // distance between eyes in 2D
  const eyeDist = Math.hypot(
    rightEye.x - leftEye.x,
    rightEye.y - leftEye.y
  );

  // --- Yaw (left/right) ---
  const noseOffsetX = noseTip.x - (leftEye.x + rightEye.x) / 2;
  const yAngle = (noseOffsetX / eyeDist) * 60;

  // --- Pitch (up/down) ---
  const noseToEyeVertical = noseTip.y - (leftEye.y + rightEye.y) / 2;
  let xAngle = (noseToEyeVertical / eyeDist) * 40;

  // add smaller z correction
  const avgEyeZ = (leftEye.z + rightEye.z) / 2;
  const zOffset = noseTip.z - avgEyeZ;
  xAngle += (zOffset * 40);

  return [xAngle, yAngle];
}

function onResults(results) {
  canvasCtx.save();
  canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
  canvasCtx.drawImage(results.image, 0, 0, canvasElement.width, canvasElement.height);

  if (results.multiFaceLandmarks && results.multiFaceLandmarks.length > 0) {
    const landmarks = results.multiFaceLandmarks[0];
    const [xAngle, yAngle] = calculateHeadPose(landmarks);

    // Status detection
    if (xAngle > 26.5 && yAngle > -4) {
      statusElement.innerText = "Not Looking Forward";
      statusElement.style.color = "red";
    } else if (xAngle > 24.5 && yAngle < 7) {
      statusElement.innerText = "Not Looking Forward";
      statusElement.style.color = "red";
    } else if (yAngle < -15 || yAngle > 15 || 
               xAngle < 15 || xAngle > 23) {
      statusElement.innerText = "Not Looking Forward";
      statusElement.style.color = "red";
    } else {
      statusElement.innerText = "Looking Forward";
      statusElement.style.color = "lime";
    }
  }
  canvasCtx.restore();
}

const faceMesh = new FaceMesh({
  locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}`,
});
faceMesh.setOptions({
  maxNumFaces: 1,
  refineLandmarks: true,
  minDetectionConfidence: 0.6,
  minTrackingConfidence: 0.6,
});
faceMesh.onResults(onResults);

const camera = new Camera(videoElement, {
  onFrame: async () => {
    await faceMesh.send({ image: videoElement });
  },
  width: 640,
  height: 480,
});
camera.start();
