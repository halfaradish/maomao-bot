import { reactive } from 'vue'

const toastState = reactive({
  show: false,
  message: '',
  type: '',
  _timer: null,
})

function showToast(message, type = '') {
  toastState.message = message
  toastState.type = type
  toastState.show = true

  if (toastState._timer) {
    clearTimeout(toastState._timer)
  }
  toastState._timer = setTimeout(() => {
    toastState.show = false
  }, 3000)
}

export function useToast() {
  return { toastState, showToast }
}
