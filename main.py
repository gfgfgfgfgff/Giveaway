import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import re

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_giveaways = {}  # {message_id: {"end_time": datetime, "winners": int, "prize": str, "emoji": str, "channel_id": int}}
        self.authorized_users = set()  # IDs des utilisateurs autorisés

    @app_commands.command(name="giveaway", description="Lance un giveaway")
    async def giveaway(
        self, 
        interaction: discord.Interaction, 
        gain: str,
        temps: str,
        salon: discord.TextChannel,
        nombre_de_gagnants: int = 1,
        emoji: str = "🎉"
    ):
        # Vérification des permissions
        if interaction.user.id not in self.authorized_users and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Vous n'êtes pas autorisé à utiliser cette commande.", ephemeral=True)
            return

        # Parser le temps
        time_unit = temps[-1]
        time_value = int(temps[:-1])
        
        if time_unit == 's':
            duration = timedelta(seconds=time_value)
        elif time_unit == 'm':
            duration = timedelta(minutes=time_value)
        elif time_unit == 'h':
            duration = timedelta(hours=time_value)
        elif time_unit == 'j':
            duration = timedelta(days=time_value)
        else:
            await interaction.response.send_message("Format de temps invalide. Utilisez s, m, h ou j", ephemeral=True)
            return

        end_time = datetime.utcnow() + duration

        # Création de l'embed
        embed = discord.Embed(
            title="**Giveaway**",
            description=f"```\nGain : {gain}\n\nDurée : {temps}\n\nNombre de gagnants : {nombre_de_gagnants}\n\n```",
            color=0xFFFFFF
        )
        
        # Ligne séparatrice continue
        embed.add_field(name="\u200b", value="─" * 50, inline=False)

        # Envoi du message
        await interaction.response.send_message("Création du giveaway...", ephemeral=True)
        giveaway_message = await salon.send(embed=embed)
        
        # Ajout du bouton
        view = discord.ui.View(timeout=None)
        
        class GiveawayButton(discord.ui.Button):
            def __init__(self, emoji):
                super().__init__(
                    style=discord.ButtonStyle.gray,
                    label="participer",
                    emoji=emoji,
                    custom_id=f"giveaway_{giveaway_message.id}"
                )
            
            async def callback(self, button_interaction: discord.Interaction):
                await button_interaction.response.send_message("Participation enregistrée !", ephemeral=True)
        
        button = GiveawayButton(emoji)
        view.add_item(button)
        
        await giveaway_message.edit(embed=embed, view=view)
        
        # Stocker les infos du giveaway
        self.active_giveaways[giveaway_message.id] = {
            "end_time": end_time,
            "winners": nombre_de_gagnants,
            "prize": gain,
            "emoji": emoji,
            "channel_id": salon.id
        }
        
        # Démarrer le timer
        self.bot.loop.create_task(self.end_giveaway(giveaway_message.id))

    @app_commands.command(name="reroll", description="Choisit de nouveaux gagnants pour un giveaway")
    async def reroll(self, interaction: discord.Interaction, id_du_message: str):
        # Vérification des permissions
        if interaction.user.id not in self.authorized_users and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Vous n'êtes pas autorisé à utiliser cette commande.", ephemeral=True)
            return

        try:
            message_id = int(id_du_message)
        except ValueError:
            await interaction.response.send_message("ID de message invalide.", ephemeral=True)
            return

        # Chercher le message
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(message_id)
                    break
                except:
                    continue
        else:
            await interaction.response.send_message("Message non trouvé.", ephemeral=True)
            return

        await self.select_winners(message, interaction)

    @app_commands.command(name="autorise", description="Autorise un utilisateur à utiliser les commandes giveaway")
    async def autorise(self, interaction: discord.Interaction, user: discord.User):
        # Seuls les admins peuvent utiliser cette commande
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Seuls les administrateurs peuvent utiliser cette commande.", ephemeral=True)
            return

        self.authorized_users.add(user.id)
        await interaction.response.send_message(f"{user.mention} est maintenant autorisé à utiliser les commandes giveaway.", ephemeral=True)

    async def end_giveaway(self, message_id: int):
        """Termine un giveaway et sélectionne les gagnants"""
        await asyncio.sleep((self.active_giveaways[message_id]["end_time"] - datetime.utcnow()).total_seconds())
        
        channel = self.bot.get_channel(self.active_giveaways[message_id]["channel_id"])
        try:
            message = await channel.fetch_message(message_id)
        except:
            return

        await self.select_winners(message)

    async def select_winners(self, message: discord.Message, interaction: discord.Interaction = None):
        """Sélectionne les gagnants d'un giveaway"""
        message_id = message.id
        
        if message_id not in self.active_giveaways:
            return

        giveaway_data = self.active_giveaways[message_id]
        winners_count = giveaway_data["winners"]
        prize = giveaway_data["prize"]

        # Récupérer les participants
        participants = []
        for reaction in message.reactions:
            if str(reaction.emoji) == giveaway_data["emoji"]:
                async for user in reaction.users():
                    if not user.bot:
                        participants.append(user)
                break

        if len(participants) < winners_count:
            winner_mentions = "Pas assez de participants"
        else:
            import random
            winners = random.sample(participants, min(winners_count, len(participants)))
            winner_mentions = " ".join([winner.mention for winner in winners])

        # Message de fin
        end_message = f"**Gagnant du giveaway** : {winner_mentions}" if winners_count == 1 else f"**Gagnants du giveaway** : {winner_mentions}"
        
        await message.reply(end_message)
        
        # Nettoyer
        del self.active_giveaways[message_id]

async def setup(bot):
    await bot.add_cog(Giveaway(bot))