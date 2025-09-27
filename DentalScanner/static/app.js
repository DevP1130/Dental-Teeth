const fileInput = document.getElementById('fileInput')
const uploadBtn = document.getElementById('uploadBtn')
const messages = document.getElementById('messages')
const resultDiv = document.getElementById('result')
const resultImg = document.getElementById('resultImg')
const cameraBtn = document.getElementById('cameraBtn')
const cameraContainer = document.getElementById('cameraContainer')
const cameraVideo = document.getElementById('cameraVideo')
const captureBtn = document.getElementById('captureBtn')
const cancelCameraBtn = document.getElementById('cancelCameraBtn')
let cameraStream = null

uploadBtn.addEventListener('click', async ()=>{
  messages.textContent = ''
  if (!fileInput.files || fileInput.files.length === 0){
    messages.textContent = 'Select a file first.'
    return
  }
  const f = fileInput.files[0]
  const fd = new FormData()
  fd.append('image', f)

  uploadBtn.disabled = true
  uploadBtn.textContent = 'Uploading...'

  try{
    const res = await fetch('/upload', {method:'POST', body: fd, headers: {'X-Requested-With':'XMLHttpRequest'}})
    const data = await res.json()
    if (!data.success){
      messages.textContent = data.error || 'Upload failed'
      uploadBtn.disabled = false
      uploadBtn.textContent = 'Upload and Scan'
      return
    }
    // show the result image
    resultImg.src = data.result_url + '?_=' + Date.now()
    resultDiv.style.display = 'block'
    uploadBtn.disabled = false
    uploadBtn.textContent = 'Upload and Scan'
  }catch(err){
    messages.textContent = err.message || 'Network error'
    uploadBtn.disabled = false
    uploadBtn.textContent = 'Upload and Scan'
  }
})

// Camera flow
cameraBtn.addEventListener('click', async ()=>{
  messages.textContent = ''
  try{
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
    cameraVideo.srcObject = cameraStream
    cameraContainer.style.display = 'block'
  }catch(err){
    messages.textContent = 'Could not access camera: ' + err.message
  }
})

cancelCameraBtn.addEventListener('click', ()=>{
  stopCamera()
})

captureBtn.addEventListener('click', async ()=>{
  if (!cameraStream) return
  // capture a frame from the video
  try{
    const track = cameraStream.getVideoTracks()[0]
    if (window.ImageCapture && typeof ImageCapture === 'function'){
      const imageCapture = new ImageCapture(track)
      if (typeof imageCapture.grabFrame === 'function'){
        const bitmap = await imageCapture.grabFrame()
        const canvas = document.createElement('canvas')
        canvas.width = bitmap.width
        canvas.height = bitmap.height
        const ctx = canvas.getContext('2d')
        ctx.drawImage(bitmap, 0, 0)
        await sendCanvasBlob(canvas)
      } else {
        // fallback to canvas drawImage from video
        await captureFromVideoToCanvas()
      }
    } else {
      // fallback to canvas drawImage from video
      await captureFromVideoToCanvas()
    }
  }catch(err){
    messages.textContent = 'Capture failed: ' + (err.message || err)
    stopCamera()
  }
})

async function captureFromVideoToCanvas(){
  const video = cameraVideo
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth || 1280
  canvas.height = video.videoHeight || 720
  const ctx = canvas.getContext('2d')
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
  await sendCanvasBlob(canvas)
}

async function sendCanvasBlob(canvas){
  return new Promise((resolve, reject)=>{
    canvas.toBlob(async (blob)=>{
      if (!blob){ messages.textContent = 'Capture failed'; reject(new Error('no blob')); return }
      const fd = new FormData()
      fd.append('image', blob, 'capture.jpg')
      uploadBtn.disabled = true
      uploadBtn.textContent = 'Uploading...'
      try{
        const res = await fetch('/upload', {method:'POST', body: fd, headers: {'X-Requested-With':'XMLHttpRequest'}})
        const data = await res.json()
        if (!data.success){ messages.textContent = data.error || 'Upload failed'; resolve(data); return }
        resultImg.src = data.result_url + '?_=' + Date.now()
        resultDiv.style.display = 'block'
        resolve(data)
      }catch(err){
        messages.textContent = err.message || 'Network error'
        reject(err)
      }finally{
        uploadBtn.disabled = false
        uploadBtn.textContent = 'Upload and Scan'
        stopCamera()
      }
    }, 'image/jpeg', 0.9)
  })
}

function stopCamera(){
  if (cameraStream){
    cameraStream.getTracks().forEach(t=>t.stop())
    cameraStream = null
  }
  cameraContainer.style.display = 'none'
}
