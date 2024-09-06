# USE FOR TESTING ONLY AND DELETE AFTER
@commands.slash_command()
    @commands.has_permissions(administrator=True)
    async def delete_channels(self, ctx: discord.ApplicationContext):
        keep_channel_id = 1112433431767437384
        guild: discord.Guild = ctx.guild
        keep_channel = guild.get_channel(keep_channel_id)

        if keep_channel is None:
            await ctx.respond(f"Channel with ID {keep_channel_id} not found.")
            return
        for channel in guild.channels:
            if channel.id != keep_channel_id:
                try:
                    await channel.delete()
                except Exception as e:
                    await ctx.respond(f"Failed to delete channel: {channel.name}. Error: {e}")
        for category in guild.categories:
            try:
                await category.delete()
            except Exception as e:
                await ctx.respond(f"Failed to delete category: {category.name}. Error: {e}")
            for channel in category.channels:
                if channel.id != keep_channel_id:
                    try:
                        await channel.delete()
                    except Exception as e:
                        await ctx.respond(f"Failed to delete channel in kept category: {channel.name}. Error: {e}")
        await ctx.respond("Finished deleting channels and categories.")