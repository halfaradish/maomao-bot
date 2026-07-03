import { reactive } from 'vue'

const confirmState = reactive({
  show: false,
  title: '',
  message: '',
  resolve: null,
  reject: null,
})

function showConfirm(title, message) {
  return new Promise((resolve, reject) => {
    confirmState.show = true
    confirmState.title = title
    confirmState.message = message
    confirmState.resolve = () => {
      confirmState.show = false
      resolve()
    }
    confirmState.reject = () => {
      confirmState.show = false
      reject(new Error('cancel'))
    }
  })
}

export function useConfirm() {
  return { confirmState, showConfirm }
}
