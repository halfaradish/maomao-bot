<template>
  <div class="page-container">
    <h3 class="page-title"><Key :size="22" />权限点</h3>

    <div class="inline-form">
      <select v-model="pluginFilter" @change="load(1)">
        <option value="">所有插件</option>
        <option v-for="p in pluginOptions" :key="p" :value="p">{{ p }}</option>
      </select>
    </div>

    <div class="table-wrap">
      <table v-if="items.length">
        <thead>
          <tr>
            <th>ID</th>
            <th>插件</th>
            <th>权限标识</th>
            <th>名称</th>
            <th>描述</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td>{{ item.id }}</td>
            <td>{{ item.plugin_name }}</td>
            <td><code>{{ item.key }}</code></td>
            <td>{{ item.name }}</td>
            <td>{{ item.description }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">暂无权限点</div>
    </div>

    <Pagination
      v-model:page="page"
      :total="total"
      :pageSize="PAGE_SIZE"
      @update:page="load"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiGet } from '../api/client'
import { useToast } from '../composables/useToast'
import Pagination from '../components/Pagination.vue'
import { PhKey as Key } from "@phosphor-icons/vue"

const { showToast } = useToast()
const PAGE_SIZE = 10

const items = ref([])
const total = ref(0)
const page = ref(1)
const pluginFilter = ref('')
const pluginOptions = ref([])

async function load(pageNum) {
  const p = pageNum || page.value
  try {
    const params = `page=${p}&size=${PAGE_SIZE}&plugin=${encodeURIComponent(pluginFilter.value)}`
    const res = await apiGet(`/permissions/points?${params}`)
    items.value = res.data.items
    total.value = res.data.total
    page.value = p
  } catch (e) {
    showToast('加载权限点列表失败', 'error')
  }
}

async function loadPlugins() {
  try {
    const res = await apiGet('/permissions/points?page=1&size=100')
    const list = res.data.items || []
    const names = [...new Set(list.map(item => item.plugin_name))]
    pluginOptions.value = names.sort()
  } catch (e) {
    showToast('加载插件列表失败', 'error')
  }
}

onMounted(() => {
  loadPlugins()
  load()
})
</script>
