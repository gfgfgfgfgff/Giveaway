import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta, UTC
import random

TOKEN = os.getenv('TOKEN')

class GiveawayBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix="!",
            intents=intents
        )
        
        self.active_giveaways = {}
        self.authorized_users = set()

    async def setup_hook(self):
        await self.add_cog(GiveawayCog(self))
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} commandes slash synchronisées")
        except Exception as e:
            print(f"❌ Erreur synchronisation: {e}")

    async def on_ready(self):
        print(f"✅ {self.user} est connecté !")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/giveaway | " + str(len(self.guilds)) + " serveurs"
            )
        )

class GiveawayView(discord.ui.View):
    """View pour le bouton de participation"""
    
    def __init__(self, emoji: str, end_time: datetime, winners: int, prize: str, channel_id: int, message_id: int = None):
        super().__init__(timeout=None)
        self.emoji = emoji
        self.end_time = end_time
        self.winners = winners
        self.prize = prize
        self.channel_id = channel_id
        self.message_id = message_id
        self.participants = set()
        self.message = None

    @discord.ui.button(label="participer", style=discord.ButtonStyle.gray)
    async def participate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Bouton de participation - toggle participation"""
        
        button.emoji = self.emoji
        
        if interaction.user.bot:
            await interaction.response.send_message("Les bots ne peuvent pas participer !", ephemeral=True)
            return

        user_id = interaction.user.id
        
        if user_id in self.participants:
            self.participants.remove(user_id)
            await interaction.response.send_message("Vous ne participez plus au giveaway", ephemeral=True)
        else:
            self.participants.add(user_id)
            await interaction.response.send_message("Votre participation est bien enregistrée", ephemeral=True)

        if self.message:
            embed = self.message.embeds[0]
            embed.set_footer(text=f"Participants: {len(self.participants)} • Fin: {self.end_time.strftime('%d/%m/%Y %H:%M:%S')}")
            await self.message.edit(embed=embed)

class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.check_expired_giveaways())

    async def check_expired_giveaways(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                current_time = datetime.now(UTC)
                expired = []
                
                for message_id, data in self.bot.active_giveaways.items():
                    if current_time >= data["end_time"]:
                        expired.append(message_id)
                
                for message_id in expired:
                    await self.end_giveaway(message_id)
                
                await asyncio.sleep(60)
            except Exception as e:
                print(f"Erreur check_expired_giveaways: {e}")
                await asyncio.sleep(60)

    @app_commands.command(name="giveaway", description="Lance un giveaway")
    async def giveaway(
        self, 
        interaction: discord.Interaction, 
        gain: str,
        temps: str,
        salon: discord.TextChannel,
        nombre_de_gagnants: app_commands.Range[int, 1, 25],
        emoji: str = "🎉"
    ):
        """Commande slash pour créer un giveaway - Nombre de gagnants OBLIGATOIRE"""
        
        if (interaction.user.id not in self.bot.authorized_users and 
            not interaction.user.guild_permissions.administrator):
            embed_error = discord.Embed(
                description="Vous n'êtes pas autorisé à utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            time_unit = temps[-1].lower()
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
                embed_error = discord.Embed(
                    description="Format de temps invalide. Utilisez `s`, `m`, `h` ou `j`",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=embed_error, ephemeral=True)
                return

            end_time = datetime.now(UTC) + duration

            embed = discord.Embed(
                title="**Giveaway**",
                description=f"```\nGain : {gain}\n\nDurée : {temps}\n\nNombre de gagnants : {nombre_de_gagnants}\n\n```",
                color=0xFFFFFF
            )
            
            embed.add_field(name="\u200b", value="───────────────────", inline=False)
            embed.set_footer(text=f"Participants: 0 • Fin: {end_time.strftime('%d/%m/%Y %H:%M:%S')}")

            view = GiveawayView(emoji, end_time, nombre_de_gagnants, gain, salon.id)
            
            giveaway_message = await salon.send(embed=embed, view=view)
            view.message = giveaway_message
            view.message_id = giveaway_message.id
            
            self.bot.active_giveaways[giveaway_message.id] = {
                "end_time": end_time,
                "winners": nombre_de_gagnants,
                "prize": gain,
                "emoji": emoji,
                "channel_id": salon.id,
                "message_id": giveaway_message.id,
                "host_id": interaction.user.id,
                "view": view,
                "participants": view.participants
            }

            embed_confirm = discord.Embed(
                description=f"Le giveaway **{gain}** est lancé dans le salon {salon.mention}",
                color=0x00FF00
            )
            await interaction.followup.send(embed=embed_confirm, ephemeral=True)

        except ValueError:
            embed_error = discord.Embed(
                description="Format de temps invalide. Exemple: `10s`, `5m`, `2h`, `1j`",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
        except Exception as e:
            embed_error = discord.Embed(
                description=f"Une erreur est survenue: {str(e)}",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)

    @app_commands.command(name="reroll", description="Choisit de nouveaux gagnants pour un giveaway")
    async def reroll(self, interaction: discord.Interaction, id_du_message: str):
        if (interaction.user.id not in self.bot.authorized_users and 
            not interaction.user.guild_permissions.administrator):
            embed_error = discord.Embed(
                description="Vous n'êtes pas autorisé à utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            message_id = int(id_du_message)
        except ValueError:
            embed_error = discord.Embed(
                description="Id du message incroyable",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
            return

        message = None
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(message_id)
                    break
                except:
                    continue

        if not message:
            embed_error = discord.Embed(
                description="Message non trouvé. Vérifiez l'ID.",
                color=0xFF0000
            )
            await interaction.followup.send(embed=embed_error, ephemeral=True)
            return

        await self.select_winners(message, interaction, reroll=True)

    @app_commands.command(name="autorise", description="Autorise un utilisateur aux commandes giveaway")
    async def autorise(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.administrator:
            embed_error = discord.Embed(
                description="Seuls les administrateurs peuvent utiliser cette commande.",
                color=0xFF0000
            )
            await interaction.response.send_message(embed=embed_error, ephemeral=True)
            return

        self.bot.authorized_users.add(user.id)
        
        embed_success = discord.Embed(
            description=f"{user.mention} est maintenant autorisé à utiliser les commandes giveaway.",
            color=0x00FF00
        )
        await interaction.response.send_message(embed=embed_success, ephemeral=True)

    async def end_giveaway(self, message_id: int):
        try:
            if message_id not in self.bot.active_giveaways:
                return

            data = self.bot.active_giveaways[message_id]
            channel = self.bot.get_channel(data["channel_id"])
            
            if not channel:
                return
                
            try:
                message = await channel.fetch_message(message_id)
            except:
                del self.bot.active_giveaways[message_id]
                return

            await self.select_winners(message)
            
        except Exception as e:
            print(f"Erreur end_giveaway: {e}")

    async def select_winners(self, message: discord.Message, interaction: discord.Interaction = None, reroll: bool = False):
        message_id = message.id
        
        if message_id not in self.bot.active_giveaways and not reroll:
            return

        if not reroll:
            data = self.bot.active_giveaways[message_id]
        else:
            embed = message.embeds[0]
            description = embed.description
            
            gain_line = [line for line in description.split('\n') if 'Gain :' in line][0]
            gain = gain_line.replace('Gain :', '').strip()
            
            winners_line = [line for line in description.split('\n') if 'Nombre de gagnants :' in line][0]
            winners_count = int(winners_line.replace('Nombre de gagnants :', '').strip())
            
            emoji = "🎉"
            if message.components and message.components[0].children:
                emoji = message.components[0].children[0].emoji or "🎉"
            
            data = {
                "winners": winners_count,
                "prize": gain,
                "emoji": emoji
            }

        winners_count = data["winners"]
        prize = data["prize"]
        emoji = data.get("emoji", "🎉")

        participants = []
        
        if not reroll and message_id in self.bot.active_giveaways:
            view = data.get("view")
            if view and hasattr(view, 'participants'):
                for user_id in view.participants:
                    user = self.bot.get_user(user_id)
                    if user:
                        participants.append(user)
        else:
            for reaction in message.reactions:
                if str(reaction.emoji) == emoji:
                    async for user in reaction.users():
                        if not user.bot:
                            participants.append(user)
                    break

        if len(participants) < winners_count:
            winner_text = "Pas assez de participants"
            winners = []
        else:
            winners = random.sample(participants, min(winners_count, len(participants)))
            winner_text = " ".join([winner.mention for winner in winners])

        # 🎯 MODIFICATION DE L'EMBED ORIGINAL
        new_embed = discord.Embed(
            title=f"**Giveaway ({prize}) terminé**",
            color=0xFFFFFF
        )
        
        if winners_count == 1:
            new_embed.add_field(name="**Gagnant**", value=winner_text, inline=False)
        else:
            new_embed.add_field(name="**Gagnants**", value=winner_text, inline=False)
        
        new_embed.set_footer(text=f"Total participants: {len(participants)} • Giveaway terminé")

        # 🎯 SUPPRESSION DU BOUTON
        try:
            await message.edit(embed=new_embed, view=None)
        except Exception as e:
            print(f"Erreur modification embed: {e}")
            await message.edit(embed=new_embed)

        # 🎯 MESSAGE DE PING
        if winners:
            if winners_count == 1:
                ping_message = f"{winner_text} a gagné **{prize}** !"
            else:
                ping_message = f"{winner_text} ont gagné **{prize}** !"
            
            await message.reply(ping_message)
        else:
            await message.reply(f"Pas assez de participants pour le giveaway **{prize}**.")

        if not reroll and message_id in self.bot.active_giveaways:
            del self.bot.active_giveaways[message_id]

        if interaction:
            embed_success = discord.Embed(
                description=f"Nouveau{'x' if winners_count > 1 else ''} gagnant{'s' if winners_count > 1 else ''} sélectionné{'s' if winners_count > 1 else ''} !",
                color=0x00FF00
            )
            await interaction.followup.send(embed=embed_success, ephemeral=True)

bot = GiveawayBot()

if __name__ == "__main__":
    if TOKEN:
        try:
            bot.run(TOKEN)
        except discord.LoginFailure:
            print("❌ Erreur: Token invalide")
        except Exception as e:
            print(f"❌ Erreur de démarrage: {e}")
    else:
        print("❌ Erreur: Token non trouvé")