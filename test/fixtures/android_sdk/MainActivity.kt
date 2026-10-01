package fixture
import android.app.Activity
interface Repository { fun fetch(): String }
class MainActivity : Activity() {
    fun reload(repository: Repository): String {
        val value = repository.fetch()
        setTitle(value)
        return value
    }
}
