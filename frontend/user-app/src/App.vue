<script>
export default {
  onLaunch() {
    // 只做启动日志；业务状态由 stores/session.js 管理
    console.info('[medpal-user-app] launched');
  },
};
</script>

<style>
@import './styles/global.css';
</style>
