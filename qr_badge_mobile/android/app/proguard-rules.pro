# Flutter / plugins (R8)
-keep class io.flutter.app.** { *; }
-keep class io.flutter.plugin.** { *; }
-keep class io.flutter.util.** { *; }
-keep class io.flutter.view.** { *; }
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }

# Play Core monolithique retiré ; l’embedding Flutter référence encore play.core.tasks.* (composants différés).
# Sans ces règles, R8 échoue en « Missing class ». Pas d’impact si vous n’utilisez pas les modules dynamiques Play.
-dontwarn com.google.android.play.core.tasks.OnFailureListener
-dontwarn com.google.android.play.core.tasks.OnSuccessListener
-dontwarn com.google.android.play.core.tasks.Task
