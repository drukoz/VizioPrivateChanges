package com.rukoz.tvhome

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.drawable.Drawable

class AppIcons(private val pm: android.content.pm.PackageManager) : IconSource {
    override fun icon(pkg: String): ByteArray? {
        val drawable: Drawable = try {
            pm.getApplicationBanner(pkg) ?: pm.getApplicationIcon(pkg)
        } catch (e: android.content.pm.PackageManager.NameNotFoundException) {
            return null
        }
        var w = drawable.intrinsicWidth
        var h = drawable.intrinsicHeight
        if (w <= 0 || h <= 0) {
            w = 320
            h = 180
        }
        if (w > 640) {
            w = 640
        }
        if (h > 360) {
            h = 360
        }
        val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        drawable.setBounds(0, 0, w, h)
        drawable.draw(Canvas(bitmap))
        val out = java.io.ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
        return out.toByteArray()
    }
}
